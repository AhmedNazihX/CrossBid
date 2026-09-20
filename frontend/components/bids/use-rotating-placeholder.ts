'use client'

import { useEffect, useState } from 'react'

import { useMediaQuery } from '@/lib/use-media-query'
import {
  ASK_PLACEHOLDER_FADE_MS,
  ASK_PLACEHOLDER_INTERVAL_MS,
  ASK_PLACEHOLDERS,
} from './ask-placeholders'

const REDUCED_MOTION_QUERY = '(prefers-reduced-motion: reduce)'

export interface RotatingPlaceholder {
  readonly text: string
  /** True while the current question is on its way out, so the caller can animate it. */
  readonly isLeaving: boolean
  /** A key that changes with the question, so an entering element remounts and re-animates. */
  readonly key: number
}

/**
 * The question showing in the empty Ask box, and whether it is leaving (ADR-0107).
 *
 * **It stops for three reasons, and each is deliberate.** As soon as the box has text, because
 * a placeholder competing with what someone is typing is noise. When the tab is hidden, because
 * a timer firing into a background tab is work nobody sees. And under
 * `prefers-reduced-motion: reduce` it never starts at all — WCAG 2.2.2 is about *auto-updating*
 * information, not only about movement, so the honest answer to "reduce motion" here is one
 * question that stays put rather than the same carousel without the slide.
 *
 * The rotation is decoration and is marked `aria-hidden` by its caller: the box's real name is
 * its `<label>`, which never changes.
 */
export function useRotatingPlaceholder(isPaused: boolean): RotatingPlaceholder {
  const prefersReducedMotion = useMediaQuery(REDUCED_MOTION_QUERY)
  const [index, setIndex] = useState(0)
  const [isLeaving, setLeaving] = useState(false)

  // `undefined` until the media query has answered; treat that as "reduce", so the first paint
  // never starts a rotation it might have to take back.
  const isFrozen = prefersReducedMotion !== false || isPaused

  useEffect(() => {
    if (isFrozen) {
      setLeaving(false)
      return
    }
    let leave: ReturnType<typeof setTimeout> | undefined
    const tick = setInterval(() => {
      if (document.visibilityState === 'hidden') {
        return
      }
      setLeaving(true)
      leave = setTimeout(() => {
        setIndex((current) => (current + 1) % ASK_PLACEHOLDERS.length)
        setLeaving(false)
      }, ASK_PLACEHOLDER_FADE_MS)
    }, ASK_PLACEHOLDER_INTERVAL_MS)
    return () => {
      clearInterval(tick)
      if (leave !== undefined) clearTimeout(leave)
    }
  }, [isFrozen])

  return { text: ASK_PLACEHOLDERS[index] ?? '', isLeaving, key: index }
}
