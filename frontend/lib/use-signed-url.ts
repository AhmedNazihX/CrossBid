'use client'

import { useCallback, useEffect, useState } from 'react'

import { describeApiError } from './api-client'
import { getDocumentUrl } from './documents'

/** Ask for a new URL this long before the current one expires. */
export const REFRESH_MARGIN_MS = 30_000
const MIN_REFRESH_DELAY_MS = 1_000

export interface SignedUrlState {
  /** The current URL, `undefined` while loading or after a failure. */
  readonly url: string | undefined
  /** One sentence for the bidder when the URL could not be fetched. */
  readonly error: string | undefined
  readonly retry: () => void
}

/**
 * Keeps a document's signed URL fresh for the source panel (S4.5.1).
 *
 * `GET /documents/{id}/url` answers with `expires_at`; the next request is scheduled
 * `REFRESH_MARGIN_MS` before that moment, so the iframe never holds a dead link. Changing
 * the document starts over; unmounting aborts the request in flight.
 */
export function useSignedUrl(documentId: string | undefined): SignedUrlState {
  const [url, setUrl] = useState<string | undefined>(undefined)
  const [error, setError] = useState<string | undefined>(undefined)
  const [attempt, setAttempt] = useState(0)

  const retry = useCallback(() => setAttempt((count) => count + 1), [])

  useEffect(() => {
    setUrl(undefined)
    setError(undefined)
    if (documentId === undefined) {
      return
    }
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout> | undefined

    const load = async () => {
      try {
        const signed = await getDocumentUrl(documentId, controller.signal)
        if (controller.signal.aborted) {
          return
        }
        setUrl(signed.url)
        setError(undefined)
        timer = setTimeout(load, refreshDelay(signed.expires_at))
      } catch (cause) {
        if (!controller.signal.aborted) {
          setError(describeApiError(cause))
        }
      }
    }

    void load()
    return () => {
      controller.abort()
      if (timer !== undefined) {
        clearTimeout(timer)
      }
    }
  }, [documentId, attempt])

  return { url, error, retry }
}

function refreshDelay(expiresAt: string): number {
  const remaining = new Date(expiresAt).getTime() - Date.now() - REFRESH_MARGIN_MS
  return Number.isNaN(remaining)
    ? MIN_REFRESH_DELAY_MS
    : Math.max(remaining, MIN_REFRESH_DELAY_MS)
}
