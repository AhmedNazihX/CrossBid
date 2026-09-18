/**
 * The cue that a run in flight is still moving (2026-09-18).
 *
 * Measured on a live run: during `extract_reqs` the *Requirements extracted* counter sat on
 * **2 for 3 min 15 s** and then jumped straight to 219, because the node writes its rows in
 * one batch at the end. A network capture over the same window showed ~27 consecutive
 * `304 Not Modified` answers to `GET /bids/{id}` — the browser was polling every two seconds
 * and the payload genuinely had not changed.
 *
 * So the screen was correct and the run was healthy, and it still read as hung: nothing on it
 * moved. These tests pin the one property that fixes that — the elapsed time advances on its
 * own clock, with **no change to the bid** — because a cue that only moves when the data moves
 * would be exactly as silent as the counter it stands in for.
 */
import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { RunLiveness } from './run-liveness'

const START = '2026-09-18T01:00:00Z'

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: false })
  vi.setSystemTime(new Date(START))
})

afterEach(() => {
  vi.useRealTimers()
})

/** Move both the wall clock and the component's interval on by `seconds`. */
function tick(seconds: number): void {
  act(() => {
    vi.advanceTimersByTime(seconds * 1_000)
  })
}

describe('RunLiveness', () => {
  test('advances every second while nothing about the bid changes', () => {
    // The whole point: the props below are never touched again.
    render(<RunLiveness startedAt={START} />)

    expect(screen.getByText('Running for 0 s')).toBeInTheDocument()

    tick(1)
    expect(screen.getByText('Running for 1 s')).toBeInTheDocument()

    tick(194)
    expect(screen.getByText('Running for 3 min 15 s')).toBeInTheDocument()
  })

  test('says it is working when the bid carries no start instant', () => {
    render(<RunLiveness startedAt={null} />)

    expect(screen.getByText('Working…')).toBeInTheDocument()
    expect(screen.queryByText(/Running for/)).not.toBeInTheDocument()
  })

  test('is hidden from assistive technology, which has the live region instead', () => {
    // The workspace already announces every phase change through an `aria-live` region. A
    // timer read out once a second would bury those announcements under its own noise.
    const { container } = render(<RunLiveness startedAt={START} />)

    expect(container.firstElementChild).toHaveAttribute('aria-hidden', 'true')
  })

  test('stops its timer when the workspace unmounts', () => {
    const clear = vi.spyOn(globalThis, 'clearInterval')
    const { unmount } = render(<RunLiveness startedAt={START} />)

    unmount()

    expect(clear).toHaveBeenCalled()
  })
})
