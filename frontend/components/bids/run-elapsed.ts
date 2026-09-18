/**
 * How long a run has been going, in words — the arithmetic behind `RunLiveness`.
 *
 * Kept apart from the component because the interesting part is a pure function of two
 * instants, and because the component's own test should be about the ticking rather than
 * about whether 195 seconds reads as `3 min 15 s`.
 *
 * The units coarsen as the number grows — seconds, then minutes and seconds, then hours and
 * minutes — so the text stays about as wide as it started and the eye has one thing to read.
 * The smaller unit is zero-padded for the same reason: `3 min 05 s` and `3 min 15 s` occupy
 * the same width, and a figure that changes width every tenth tick draws attention to its own
 * layout rather than to the fact that it moved.
 */
const MS_PER_SECOND = 1_000
const SECONDS_PER_MINUTE = 60
const SECONDS_PER_HOUR = 3_600

/** Two digits, so the text does not change width as the small unit rolls over. */
function padded(value: number): string {
  return value.toString().padStart(2, '0')
}

/**
 * `startedAt` to `now` as a short duration, or `null` when there is no usable start instant.
 *
 * `null` rather than a guess: `BidResponse.created_at` is nullable, and a bid whose start is
 * unknown should say it is working rather than claim a duration measured from nothing.
 *
 * Never negative. A browser clock a few seconds behind the server's would otherwise render a
 * run that has not started yet, which is alarming and is never the truth — the bid exists, so
 * it started.
 */
export function formatElapsed(startedAt: string | null | undefined, now: Date): string | null {
  if (startedAt === null || startedAt === undefined || startedAt.length === 0) {
    return null
  }
  const started = new Date(startedAt)
  if (Number.isNaN(started.getTime())) {
    return null
  }

  const elapsedMs = now.getTime() - started.getTime()
  const total = Math.max(0, Math.floor(elapsedMs / MS_PER_SECOND))

  if (total < SECONDS_PER_MINUTE) {
    return `${total} s`
  }
  if (total < SECONDS_PER_HOUR) {
    const minutes = Math.floor(total / SECONDS_PER_MINUTE)
    return `${minutes} min ${padded(total % SECONDS_PER_MINUTE)} s`
  }
  const hours = Math.floor(total / SECONDS_PER_HOUR)
  const minutes = Math.floor((total % SECONDS_PER_HOUR) / SECONDS_PER_MINUTE)
  return `${hours} hr ${padded(minutes)} min`
}
