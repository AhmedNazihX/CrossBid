/**
 * The paging hook the three bid lists and the documents panel share — audit finding M13.
 *
 * The lists were unbounded, then silently truncated: the dashboard showed the newest 200 and
 * nothing in the answer said there were more. The API now pages with an opaque cursor, and
 * this is the browser's half — accumulate what has been fetched, remember where to continue,
 * and stop offering more when there is none.
 *
 * Three things here are easy to get wrong and quiet about it:
 *
 * - **Losing the first page when the second arrives.** The list must accumulate, not replace.
 * - **Asking twice for the same page.** A second click while the first is in flight would
 *   append the same rows again.
 * - **Offering "Load more" on the last page.** `nextCursor` absent is the only signal; a full
 *   page is not one, which is the whole reason the API returns the field.
 */
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, test, vi } from 'vitest'

import { usePagedList, type PageOf } from './use-paged-list'

interface Row {
  readonly id: string
}

const PAGE_ONE: PageOf<Row> = {
  items: [{ id: 'a' }, { id: 'b' }],
  nextCursor: 'cursor-one',
}
const PAGE_TWO: PageOf<Row> = { items: [{ id: 'c' }], nextCursor: undefined }

afterEach(() => {
  vi.restoreAllMocks()
})

describe('usePagedList', () => {
  test('it loads the first page on mount', async () => {
    // Arrange
    const fetchPage = vi.fn().mockResolvedValue(PAGE_ONE)

    // Act
    const { result } = renderHook(() => usePagedList<Row>(fetchPage))

    // Assert
    await waitFor(() => expect(result.current.phase).toBe('loaded'))
    expect(result.current.items).toEqual(PAGE_ONE.items)
    expect(fetchPage).toHaveBeenCalledWith(undefined, expect.any(AbortSignal))
  })

  test('the first page offers more when the API says there is more', async () => {
    const fetchPage = vi.fn().mockResolvedValue(PAGE_ONE)

    const { result } = renderHook(() => usePagedList<Row>(fetchPage))

    await waitFor(() => expect(result.current.hasMore).toBe(true))
  })

  test('a last page offers nothing more, even when it is full', async () => {
    /** `nextCursor` is the only signal. Counting rows against the page size would offer a
     * "Load more" that fetches an empty page — which is what the API returns the field for. */
    // Arrange
    const fetchPage = vi
      .fn()
      .mockResolvedValue({ items: PAGE_ONE.items, nextCursor: undefined })

    // Act
    const { result } = renderHook(() => usePagedList<Row>(fetchPage))

    // Assert
    await waitFor(() => expect(result.current.phase).toBe('loaded'))
    expect(result.current.hasMore).toBe(false)
  })

  test('loading more appends rather than replacing', async () => {
    // Arrange
    const fetchPage = vi.fn().mockResolvedValueOnce(PAGE_ONE).mockResolvedValueOnce(PAGE_TWO)
    const { result } = renderHook(() => usePagedList<Row>(fetchPage))
    await waitFor(() => expect(result.current.phase).toBe('loaded'))

    // Act
    await act(async () => {
      result.current.loadMore()
    })

    // Assert
    await waitFor(() => expect(result.current.items).toHaveLength(3))
    expect(result.current.items.map((row) => row.id)).toEqual(['a', 'b', 'c'])
  })

  test('loading more follows the cursor the API gave', async () => {
    // Arrange
    const fetchPage = vi.fn().mockResolvedValueOnce(PAGE_ONE).mockResolvedValueOnce(PAGE_TWO)
    const { result } = renderHook(() => usePagedList<Row>(fetchPage))
    await waitFor(() => expect(result.current.phase).toBe('loaded'))

    // Act
    await act(async () => {
      result.current.loadMore()
    })

    // Assert
    expect(fetchPage).toHaveBeenLastCalledWith('cursor-one', expect.any(AbortSignal))
  })

  test('the last page ends the offer', async () => {
    // Arrange
    const fetchPage = vi.fn().mockResolvedValueOnce(PAGE_ONE).mockResolvedValueOnce(PAGE_TWO)
    const { result } = renderHook(() => usePagedList<Row>(fetchPage))
    await waitFor(() => expect(result.current.phase).toBe('loaded'))

    // Act
    await act(async () => {
      result.current.loadMore()
    })

    // Assert
    await waitFor(() => expect(result.current.hasMore).toBe(false))
  })

  test('a second loadMore while one is in flight does not fetch twice', async () => {
    /** Two clicks on the button would otherwise append the same page twice, and the row keys
     * would collide. */
    // Arrange
    let release: (page: PageOf<Row>) => void = () => {}
    const fetchPage = vi
      .fn()
      .mockResolvedValueOnce(PAGE_ONE)
      .mockImplementationOnce(
        () =>
          new Promise<PageOf<Row>>((resolve) => {
            release = resolve
          })
      )
    const { result } = renderHook(() => usePagedList<Row>(fetchPage))
    await waitFor(() => expect(result.current.phase).toBe('loaded'))

    // Act
    act(() => {
      result.current.loadMore()
      result.current.loadMore()
    })
    await act(async () => {
      release(PAGE_TWO)
    })

    // Assert
    expect(fetchPage).toHaveBeenCalledTimes(2)
    await waitFor(() => expect(result.current.items).toHaveLength(3))
  })

  test('a failure on the first page is a failed list', async () => {
    // Arrange
    const fetchPage = vi.fn().mockRejectedValue(new Error('the network went away'))

    // Act
    const { result } = renderHook(() => usePagedList<Row>(fetchPage))

    // Assert
    await waitFor(() => expect(result.current.phase).toBe('failed'))
    expect(result.current.message).toContain('the network went away')
  })

  test('a failure loading more keeps the rows already on the screen', async () => {
    /** Losing two pages of reading because the third failed is the worse answer. */
    // Arrange
    const fetchPage = vi
      .fn()
      .mockResolvedValueOnce(PAGE_ONE)
      .mockRejectedValueOnce(new Error('the network went away'))
    const { result } = renderHook(() => usePagedList<Row>(fetchPage))
    await waitFor(() => expect(result.current.phase).toBe('loaded'))

    // Act
    await act(async () => {
      result.current.loadMore()
    })

    // Assert
    await waitFor(() => expect(result.current.message).toBeDefined())
    expect(result.current.phase).toBe('loaded')
    expect(result.current.items).toEqual(PAGE_ONE.items)
  })

  test('loadMore on a last page does nothing at all', async () => {
    // Arrange
    const fetchPage = vi
      .fn()
      .mockResolvedValue({ items: PAGE_TWO.items, nextCursor: undefined })
    const { result } = renderHook(() => usePagedList<Row>(fetchPage))
    await waitFor(() => expect(result.current.phase).toBe('loaded'))

    // Act
    await act(async () => {
      result.current.loadMore()
    })

    // Assert
    expect(fetchPage).toHaveBeenCalledTimes(1)
  })
})
