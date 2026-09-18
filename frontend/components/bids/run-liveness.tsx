'use client'

import { useEffect, useState } from 'react'

import { formatElapsed } from './run-elapsed'

/**
 * "Running for 3 min 15 s" — the one thing on a running workspace that moves by itself.
 *
 * **No artboard covers this.** `docs/design/canvas/Main.dc.html` draws the workspace in its
 * settled state only; it has no reading, extracting or checking state to implement, so there
 * is nothing to cite here (ADR-0014 asks for the citation *or* this note).
 *
 * **Why it exists.** Measured on a live run: the *Requirements extracted* card sat on **2 for
 * 3 min 15 s** and then jumped to 219, because `extract_reqs` writes its rows in one batch at
 * the end. Over the same window the browser polled `GET /bids/{id}` every two seconds and got
 * ~27 consecutive `304 Not Modified` — the poll was healthy and the payload really had not
 * changed. Every existing signal on that screen is derived from the payload, so every one of
 * them froze together, and a working run was indistinguishable from a hung one.
 *
 * This counts off the wall clock instead, so it keeps moving through a node that reports
 * nothing. That is the whole design: a cue driven by the data would have gone quiet at
 * exactly the moment it was needed.
 *
 * **Why no spinner.** `app/globals.css` defines no animation tokens, and its `@theme inline`
 * block opens with `--color-*: initial`, so an unproven utility class emits no declaration at
 * all rather than an error — which is how the Review verdict button once shipped invisible.
 * A number that changes every second is motion that cannot fail that way.
 *
 * **Why `aria-hidden`.** The workspace already announces phase changes through an
 * `aria-live="polite"` region. A timer read aloud once a second would bury them.
 */
const TICK_MS = 1_000

export interface RunLivenessProps {
  /** `BidResponse.created_at` — when the run started. Nullable, as the API declares it. */
  readonly startedAt: string | null | undefined
}

export function RunLiveness({ startedAt }: RunLivenessProps) {
  const [now, setNow] = useState(() => new Date())

  useEffect(() => {
    const timer = setInterval(() => {
      setNow(new Date())
    }, TICK_MS)
    return () => {
      clearInterval(timer)
    }
  }, [])

  const elapsed = formatElapsed(startedAt, now)

  return (
    <span aria-hidden="true" className="[font:var(--type-body-sm)] text-text-muted">
      {elapsed === null ? 'Working…' : `Running for ${elapsed}`}
    </span>
  )
}
