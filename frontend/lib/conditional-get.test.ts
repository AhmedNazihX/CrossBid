/**
 * The conditional poll — audit finding M13.
 *
 * `GET /bids/{id}` is polled every two seconds for the whole length of a run and answers with
 * the bid, every requirement, every document and every matrix row: 144 rows on the FR pack,
 * 284 on the DE one. Nearly all of those answers are byte-identical to the one before. The
 * API now sends an `ETag` and honours `If-None-Match`, so an unchanged poll is a 304 with no
 * body — but only if the browser actually echoes the tag back, which is what this pins.
 *
 * Two things are easy to get wrong here and both are silent:
 *
 * - **Not sending the header at all.** Everything still works; the saving simply never
 *   happens, and nothing anywhere says so.
 * - **Returning a new object on 304.** The value is identical, but React compares by
 *   identity, so a fresh object re-renders the whole workspace every two seconds — which is
 *   most of the cost the 304 was supposed to remove.
 */
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { conditionalGet, type Conditional } from './conditional-get'

const TAG = 'W/"a3f1b2c3d4e5f607"'
const NEXT_TAG = 'W/"0706f5e4d3c2b1f3"'

function answer(
  body: unknown,
  { status = 200, etag }: { status?: number; etag?: string } = {}
) {
  return {
    status,
    body,
    headers: new Headers(etag === undefined ? {} : { ETag: etag }),
  }
}

describe('conditionalGet', () => {
  let fetcher: ReturnType<typeof vi.fn>

  beforeEach(() => {
    fetcher = vi.fn()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  test('the first call holds nothing and sends no If-None-Match', async () => {
    // Arrange
    fetcher.mockResolvedValue(answer({ id: 'one' }, { etag: TAG }))

    // Act
    await conditionalGet(fetcher, undefined)

    // Assert
    expect(fetcher).toHaveBeenCalledWith(undefined)
  })

  test('the first call keeps the value and the tag that came with it', async () => {
    // Arrange
    fetcher.mockResolvedValue(answer({ id: 'one' }, { etag: TAG }))

    // Act
    const held = await conditionalGet(fetcher, undefined)

    // Assert
    expect(held).toEqual({ value: { id: 'one' }, etag: TAG })
  })

  test('the next call sends back the tag it was given', async () => {
    // Arrange
    const held: Conditional<unknown> = { value: { id: 'one' }, etag: TAG }
    fetcher.mockResolvedValue(answer(undefined, { status: 304, etag: TAG }))

    // Act
    await conditionalGet(fetcher, held)

    // Assert
    expect(fetcher).toHaveBeenCalledWith(TAG)
  })

  test('a 304 returns the very same object, not a copy of it', async () => {
    // Arrange: identity is the point — React bails out of a render when it is preserved.
    const held: Conditional<unknown> = { value: { id: 'one' }, etag: TAG }
    fetcher.mockResolvedValue(answer(undefined, { status: 304, etag: TAG }))

    // Act
    const again = await conditionalGet(fetcher, held)

    // Assert
    expect(again).toBe(held)
    expect(again.value).toBe(held.value)
  })

  test('a changed answer replaces both the value and the tag', async () => {
    // Arrange
    const held: Conditional<unknown> = { value: { id: 'one' }, etag: TAG }
    fetcher.mockResolvedValue(answer({ id: 'two' }, { etag: NEXT_TAG }))

    // Act
    const again = await conditionalGet(fetcher, held)

    // Assert
    expect(again).toEqual({ value: { id: 'two' }, etag: NEXT_TAG })
  })

  test('an answer with no ETag still yields its body, with nothing held for next time', async () => {
    /** A proxy that strips the header, or CORS not exposing it: the poll must keep working,
     * unconditionally, rather than throwing on every tick. */
    // Arrange
    fetcher.mockResolvedValue(answer({ id: 'one' }))

    // Act
    const held = await conditionalGet(fetcher, undefined)

    // Assert
    expect(held.value).toEqual({ id: 'one' })
    expect(held.etag).toBeUndefined()
  })

  test('holding a value with no tag sends no If-None-Match on the next call', async () => {
    // Arrange
    const held: Conditional<unknown> = { value: { id: 'one' }, etag: undefined }
    fetcher.mockResolvedValue(answer({ id: 'one' }))

    // Act
    await conditionalGet(fetcher, held)

    // Assert
    expect(fetcher).toHaveBeenCalledWith(undefined)
  })

  test('a 304 with nothing held is a protocol error, not a silent undefined', async () => {
    /** The server may only answer 304 to a conditional request, so this cannot happen without
     * something being wrong; returning `undefined` as the value would put it on the screen. */
    // Arrange
    fetcher.mockResolvedValue(answer(undefined, { status: 304, etag: TAG }))

    // Act / Assert
    await expect(conditionalGet(fetcher, undefined)).rejects.toThrow(/304/)
  })
})
