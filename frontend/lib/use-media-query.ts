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

/**
 * Tailwind's `xl`, which is where the workspace grows its 380 px verdict rail.
 *
 * The rail is the one place the verdict panel is too narrow for the artboard's two columns, so
 * it is also the only place the panel takes its `rail` layout (ADR-0106). Below this the grid
 * is one column, the panel has the full content width, and the artboard's shape is right —
 * which is why this cannot be keyed on `SHELL_MEDIA_QUERY`.
 */
export const RAIL_MEDIA_QUERY = '(min-width: 1280px)'
