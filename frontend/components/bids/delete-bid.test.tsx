/**
 * Deleting a tender analysis, and what the bidder is told before they do.
 *
 * Deleting is irreversible and it is *asymmetric*: the analysis goes, the uploaded documents
 * stay and become deletable again, and the money already spent stays in the cost console. A
 * confirmation that only said "are you sure?" would leave a bidder guessing which of the three
 * they were about to lose — and the one they most fear losing, their own files, is the one that
 * survives.
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { deleteBid } from '@/lib/bids'

import { DeleteBid } from './delete-bid'

vi.mock('@/lib/bids', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/bids')>()
  return { ...actual, deleteBid: vi.fn() }
})

const onDeleted = vi.fn()

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(deleteBid).mockResolvedValue(undefined)
})

describe('DeleteBid', () => {
  test('asks before deleting, and names what stays as well as what goes', async () => {
    const user = userEvent.setup()
    render(<DeleteBid bidId="bid-1" title="618320-2026" onDeleted={onDeleted} />)

    await user.click(screen.getByRole('button', { name: /delete analysis/i }))

    const question = screen.getByRole('alertdialog')
    expect(question).toHaveTextContent('618320-2026')
    expect(question).toHaveTextContent(/documents.*kept|kept.*documents/i)
    expect(deleteBid).not.toHaveBeenCalled()
  })

  test('deletes once confirmed, and tells the caller', async () => {
    const user = userEvent.setup()
    render(<DeleteBid bidId="bid-1" title="618320-2026" onDeleted={onDeleted} />)

    await user.click(screen.getByRole('button', { name: /delete analysis/i }))
    await user.click(screen.getByRole('button', { name: /^delete$/i }))

    await waitFor(() => expect(deleteBid).toHaveBeenCalledWith('bid-1'))
    expect(onDeleted).toHaveBeenCalledOnce()
  })

  test('backing out deletes nothing', async () => {
    const user = userEvent.setup()
    render(<DeleteBid bidId="bid-1" title="618320-2026" onDeleted={onDeleted} />)

    await user.click(screen.getByRole('button', { name: /delete analysis/i }))
    await user.click(screen.getByRole('button', { name: /keep it/i }))

    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    expect(deleteBid).not.toHaveBeenCalled()
  })

  test('a running bid is refused with the reason the server gave', async () => {
    // The 409 carries a sentence about the run still going; a generic "could not delete"
    // would drop the one fact that tells the bidder to wait rather than retry.
    const user = userEvent.setup()
    vi.mocked(deleteBid).mockRejectedValue(
      Object.assign(
        new Error('This analysis is still running. Wait for it to finish or fail.'),
        {
          status: 409,
        }
      )
    )
    render(<DeleteBid bidId="bid-1" title="618320-2026" onDeleted={onDeleted} />)

    await user.click(screen.getByRole('button', { name: /delete analysis/i }))
    await user.click(screen.getByRole('button', { name: /^delete$/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/still running/i)
    expect(onDeleted).not.toHaveBeenCalled()
  })
})
