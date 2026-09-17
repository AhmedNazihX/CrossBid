'use client'

import { useCallback, useEffect, useRef, useState } from 'react'

import { describeApiError } from './api-client'

/**
 * One list, fetched a page at a time — audit finding M13.
 *
 * The bid list truncated silently at 200 and the document list had no limit at all. Both now
 * page with an opaque cursor, and all four screens that read them (the dashboard, the bids
 * table, the verdicts list, the documents panel) had the same three-state
 * loading/loaded/failed shape written out separately. This is that shape once, with the
 * cursor kept inside it.
 *
 * **`nextCursor` is the only signal that there is more.** A full page is not one: the API
 * fetches `limit + 1` rows precisely so it can tell a full page from a last one, and
 * re-deriving that in the browser by counting rows would offer a "Load more" that fetches
 * nothing.
 *
 * **A failure while loading more keeps what is on the screen.** Dropping two pages of reading
 * because the third request failed is the worse answer; the rows stay, the message appears
 * beside them, and the cursor is untouched so the same click can be tried again.
 */

/** One page as the `lib/` wrappers return it. */
export interface PageOf<T> {
  readonly items: readonly T[]
  readonly nextCursor: string | undefined
}

/** Fetches one page; `cursor` is `undefined` for the first. */
export type FetchPage<T> = (
  cursor: string | undefined,
  signal: AbortSignal
) => Promise<PageOf<T>>

export interface PagedList<T> {
  readonly phase: 'loading' | 'loaded' | 'failed'
  readonly items: readonly T[]
  /** Set while the first page failed, or beside the rows when a later page did. */
  readonly message: string | undefined
  readonly hasMore: boolean
  readonly isLoadingMore: boolean
  readonly loadMore: () => void
}

export function usePagedList<T>(fetchPage: FetchPage<T>): PagedList<T> {
  const [items, setItems] = useState<readonly T[]>([])
  const [phase, setPhase] = useState<'loading' | 'loaded' | 'failed'>('loading')
  const [message, setMessage] = useState<string | undefined>(undefined)
  const [cursor, setCursor] = useState<string | undefined>(undefined)
  const [isLoadingMore, setIsLoadingMore] = useState(false)
  /** A ref, not the state above: two clicks in one tick read the same state value. */
  const inFlight = useRef(false)

  useEffect(() => {
    const controller = new AbortController()
    inFlight.current = true
    fetchPage(undefined, controller.signal)
      .then((page) => {
        if (controller.signal.aborted) return
        setItems(page.items)
        setCursor(page.nextCursor)
        setPhase('loaded')
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return
        setMessage(describeApiError(cause))
        setPhase('failed')
      })
      .finally(() => {
        inFlight.current = false
      })
    return () => controller.abort()
  }, [fetchPage])

  const loadMore = useCallback(() => {
    if (cursor === undefined || inFlight.current) return
    inFlight.current = true
    setIsLoadingMore(true)
    setMessage(undefined)
    const controller = new AbortController()
    fetchPage(cursor, controller.signal)
      .then((page) => {
        setItems((held) => [...held, ...page.items])
        setCursor(page.nextCursor)
      })
      .catch((cause: unknown) => {
        // The rows already fetched stay; only the message is new.
        setMessage(describeApiError(cause))
      })
      .finally(() => {
        inFlight.current = false
        setIsLoadingMore(false)
      })
  }, [cursor, fetchPage])

  return {
    phase,
    items,
    message,
    hasMore: cursor !== undefined,
    isLoadingMore,
    loadMore,
  }
}
