'use client'

import { useCallback, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Notice } from '@/components/ui/notice'
import { describeApiError } from '@/lib/api-client'
import { deleteBid } from '@/lib/bids'

export interface DeleteBidProps {
  readonly bidId: string
  /** What the bidder calls this analysis, so the question names the thing it is about. */
  readonly title: string
  /** Called once the server has confirmed it is gone. */
  readonly onDeleted: () => void
  readonly className?: string
}

/**
 * Delete one tender analysis, asked twice and answered honestly about what survives.
 *
 * **The confirmation names what stays, not only what goes**, because the asymmetry is the whole
 * point and it runs opposite to the fear. What goes is the analysis: the requirements, the
 * matrix, the verdict, the review and the corpus it searched. What stays is the bidder's own
 * uploaded documents — and, having been detached from the bid, they become deletable again,
 * which is the other half of what "delete this tender" means. The spend stays in the cost
 * console with the bid's name gone. A bidder reading "are you sure?" would reasonably assume
 * their files were about to go with it.
 *
 * **The server's refusal is shown as the server wrote it.** A 409 while the run is going says
 * to wait rather than to retry, and a generic "could not delete" would throw that away — the
 * same reason `sign-in-card.tsx` shows Supabase's own message rather than paraphrasing it.
 *
 * `alertdialog` rather than a bare row of buttons: this is a destructive question that wants an
 * answer before anything else, and the role is what tells a screen reader so.
 */
export function DeleteBid({ bidId, title, onDeleted, className }: DeleteBidProps) {
  const [isConfirming, setIsConfirming] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [failure, setFailure] = useState<string | undefined>(undefined)

  const remove = useCallback(async () => {
    setIsDeleting(true)
    setFailure(undefined)
    try {
      await deleteBid(bidId)
      setIsConfirming(false)
      onDeleted()
    } catch (error) {
      setFailure(describeApiError(error))
    } finally {
      setIsDeleting(false)
    }
  }, [bidId, onDeleted])

  if (!isConfirming) {
    return (
      <Button
        type="button"
        variant="secondary"
        size="sm"
        className={className}
        onClick={() => setIsConfirming(true)}
      >
        Delete analysis
      </Button>
    )
  }

  return (
    <div
      role="alertdialog"
      aria-label={`Delete the analysis of ${title}`}
      className="flex flex-col gap-2"
    >
      <p className="m-0 [font:var(--type-body-sm)] text-text-primary">
        Delete the analysis of <strong className="font-medium">{title}</strong>? Its
        requirements, matrix and verdict go and cannot be brought back. The documents you
        uploaded are <strong className="font-medium">kept</strong>, and deleting this frees them
        to be deleted too.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="button"
          variant="danger"
          size="sm"
          disabled={isDeleting}
          onClick={() => void remove()}
        >
          {isDeleting ? 'Deleting…' : 'Delete'}
        </Button>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          disabled={isDeleting}
          onClick={() => {
            setIsConfirming(false)
            setFailure(undefined)
          }}
        >
          Keep it
        </Button>
      </div>
      {failure !== undefined && (
        <Notice tone="danger" title="Not deleted">
          {failure}
        </Notice>
      )}
    </div>
  )
}
