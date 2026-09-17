'use client'

import { Button } from '@/components/ui/button'
import { Notice } from '@/components/ui/notice'

/**
 * The control that follows a list's cursor — audit finding M13.
 *
 * The bid list truncated at 200 and the document list had no limit at all, and neither said
 * so. Both page now, and this is what makes the next page reachable rather than theoretical.
 *
 * It renders nothing at all on a last page. `hasMore` comes from the API's `next_cursor`,
 * never from counting rows against the page size: a full page is not evidence of another one,
 * which is the reason the field exists.
 *
 * A failure while loading more is shown here, beside the rows already fetched, rather than
 * replacing the list — losing two pages of reading because the third request failed is the
 * worse answer, and the same button retries.
 */
export interface LoadMoreProps {
  readonly hasMore: boolean
  readonly isLoadingMore: boolean
  /** A failure from the *last* request, when rows are already on the screen. */
  readonly message?: string
  readonly onLoadMore: () => void
  /** What is being loaded, lower case and plural: "tenders", "documents". */
  readonly noun: string
}

export function LoadMore({ hasMore, isLoadingMore, message, onLoadMore, noun }: LoadMoreProps) {
  if (!hasMore && message === undefined) return null
  return (
    <div className="mt-4 flex flex-col gap-3">
      {message !== undefined && (
        <Notice tone="danger" title={`More ${noun} could not be loaded`}>
          {message}
        </Notice>
      )}
      {hasMore && (
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={onLoadMore}
          disabled={isLoadingMore}
          className="self-start"
        >
          {isLoadingMore ? `Loading more ${noun}…` : `Load more ${noun}`}
        </Button>
      )}
    </div>
  )
}
