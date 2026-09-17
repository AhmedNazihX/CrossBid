/**
 * Conditional GET — audit finding M13, the browser half.
 *
 * `GET /bids/{id}` is polled every two seconds for the whole length of a run and answers with
 * the bid, every requirement, every document and every matrix row. Nearly every one of those
 * answers is identical to the one before. The API sends an `ETag`; echoing it back as
 * `If-None-Match` turns an unchanged poll into a 304 with no body at all.
 *
 * **What is held, and where.** One `{ value, etag }` pair per caller, kept by the caller — a
 * ref in the polling hook, not a module-level cache. A module cache would outlive the
 * workspace it belongs to, leak between two bids open in two tabs, and be invisible to a
 * test.
 *
 * **Why a 304 returns the identical object.** React compares by identity, so handing back a
 * fresh object with equal contents re-renders the entire workspace every two seconds — which
 * is most of the cost the 304 exists to remove. Returning the same reference makes the
 * `useState` update a no-op, and the saving is real rather than nominal.
 *
 * The `ETag` header is only readable cross-origin because the API names it in
 * `expose_headers`, and `If-None-Match` is only sendable because it names it in
 * `allow_headers`; half of that pair makes this silently unconditional (ADR-0093).
 */

/** A value and the entity tag the API sent with it. `etag` is absent when it sent none. */
export interface Conditional<T> {
  readonly value: T
  readonly etag: string | undefined
}

/** One conditional answer, as `apiConditionalGet` reports it. */
export interface ConditionalAnswer {
  readonly status: number
  readonly body: unknown
  readonly headers: Headers
}

/** Makes the request, sending `ifNoneMatch` when there is one to send. */
export type ConditionalFetcher = (ifNoneMatch: string | undefined) => Promise<ConditionalAnswer>

const NOT_MODIFIED = 304

/**
 * Fetches, conditionally on what `held` already contains.
 *
 * Returns `held` itself — same reference — when the answer is 304, and a new pair otherwise.
 *
 * @throws Error when the API answers 304 to a request that sent no `If-None-Match`. That is
 * not a case to paper over with an empty value: the server may only answer 304 to a
 * conditional request, so it means the request and the answer disagree, and the alternative
 * is rendering `undefined` where a bid should be.
 */
export async function conditionalGet<T>(
  fetcher: ConditionalFetcher,
  held: Conditional<T> | undefined
): Promise<Conditional<T>> {
  const answer = await fetcher(held?.etag)
  if (answer.status === NOT_MODIFIED) {
    if (held === undefined) {
      throw new Error('The API answered 304 to a request that asked for no condition.')
    }
    return held
  }
  return { value: answer.body as T, etag: answer.headers.get('ETag') ?? undefined }
}
