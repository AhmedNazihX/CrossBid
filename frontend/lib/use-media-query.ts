'use client'

import { useSyncExternalStore } from 'react'

/**
 * Whether a CSS media query matches, as React state. The server has no viewport, so the
 * server snapshot is `undefined`; callers render nothing viewport-dependent until the value
 * is known, which avoids a hydration mismatch and a flash of the wrong layout.
 */
export function useMediaQuery(query: string): boolean | undefined {
  return useSyncExternalStore(
    (onChange) => {
      const media = window.matchMedia(query)
      media.addEventListener('change', onChange)
      return () => media.removeEventListener('change', onChange)
    },
    () => window.matchMedia(query).matches,
    () => undefined
  )
}

/** The shell breakpoint of `globals.css`: sidebar and content frame from 900 px up. */
export const SHELL_MEDIA_QUERY = '(min-width: 900px)'
