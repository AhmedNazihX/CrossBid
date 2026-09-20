/**
 * Choosing documents in the table and deleting them from the toolbar above it.
 *
 * Two rules are under test, and both came from something that went wrong.
 *
 * The first is the server's (ADR-0088): a document a bid has claimed cannot be deleted,
 * because that run's requirements cite its pages and the API answers 409. Its box is disabled
 * rather than ticked-and-refused.
 *
 * The second is a layout rule with teeth. The first delete control shipped as the table's
 * last column, and `DataTable` scrolls horizontally: measured at a 1100 px window, the
 * control sat 106 px past the right edge and could not be reached without dragging the table
 * sideways. The action now lives above the table and the tick box leads the row, so neither
 * can be clipped away.
 *
 * The rows are `ready`, so `usePolling` never fetches and no network stub is needed for the
 * table; `deleteDocument` is stubbed because that is the call under test.
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { documentFixture } from '@/e2e/support/fixtures'

import { DeleteSelected } from './delete-selected'
import { DocumentsTable } from './documents-table'
import type { DocumentResponse } from '@/lib/documents'

const { deleteDocumentMock } = vi.hoisted(() => ({ deleteDocumentMock: vi.fn() }))

vi.mock('@/lib/documents', async () => {
  const actual = await vi.importActual<typeof import('@/lib/documents')>('@/lib/documents')
  return { ...actual, deleteDocument: deleteDocumentMock }
})

const FIRST = documentFixture({
  id: '44444444-4444-4444-8444-444444444441',
  name: 'Leistungsbeschreibung.pdf',
  bid_count: 0,
})

const SECOND = documentFixture({
  id: '44444444-4444-4444-8444-444444444443',
  name: 'Handelsregisterauszug.pdf',
  bid_count: 0,
})

const IN_A_BID = documentFixture({
  id: '44444444-4444-4444-8444-444444444442',
  name: 'Rahmenvereinbarung.pdf',
  bid_count: 2,
})

/** Two above, one here: an implementation that hard-codes the singular cannot pass both. */
const IN_ONE_BID = documentFixture({
  id: '44444444-4444-4444-8444-444444444444',
  name: 'Vergabeunterlagen.pdf',
  bid_count: 1,
})

beforeEach(() => {
  deleteDocumentMock.mockReset()
  deleteDocumentMock.mockResolvedValue(undefined)
})

/** The panel's own wiring, in miniature: the table selects, the toolbar deletes. */
function Harness({
  documents,
  onDeleted = vi.fn(),
}: {
  documents: readonly DocumentResponse[]
  onDeleted?: (deleted: readonly DocumentResponse[]) => void
}) {
  const [selectedIds, setSelectedIds] = useState<ReadonlySet<string>>(new Set())
  return (
    <div>
      <DeleteSelected
        selected={documents.filter((d) => selectedIds.has(d.id))}
        onDeleted={onDeleted}
      />
      <DocumentsTable
        documents={documents}
        onDocumentChange={vi.fn()}
        selectedIds={selectedIds}
        onSelectedChange={(document, isSelected) =>
          setSelectedIds((current) => {
            const next = new Set(current)
            if (isSelected) next.add(document.id)
            else next.delete(document.id)
            return next
          })
        }
        // Stores what the table hands over, exactly as the panel does. Deciding which
        // documents are selectable HERE is what made this test unable to fail: it measured
        // its own filter and never touched the component's.
        onSelectAll={(chosen) => setSelectedIds(new Set(chosen.map((d) => d.id)))}
      />
    </div>
  )
}

describe('choosing documents and deleting them', () => {
  test('the delete action is outside the table, so a narrow window cannot clip it', () => {
    render(<Harness documents={[FIRST]} />)

    const table = screen.getByRole('table')
    const count = screen.getByText('No documents selected')

    expect(table.contains(count)).toBe(false)
  })

  test('each tick box names its document', () => {
    render(<Harness documents={[FIRST]} />)

    expect(
      screen.getByRole('checkbox', { name: 'Select Leistungsbeschreibung.pdf' })
    ).toBeInTheDocument()
  })

  test('ticking a document counts it', async () => {
    const user = userEvent.setup()
    render(<Harness documents={[FIRST, SECOND]} />)

    await user.click(screen.getByRole('checkbox', { name: 'Select Leistungsbeschreibung.pdf' }))

    expect(screen.getByText('1 document selected')).toBeInTheDocument()
  })

  test('deleting asks first, with the count in the question', async () => {
    const user = userEvent.setup()
    render(<Harness documents={[FIRST, SECOND]} />)

    await user.click(screen.getByRole('checkbox', { name: 'Select Leistungsbeschreibung.pdf' }))
    await user.click(screen.getByRole('checkbox', { name: 'Select Handelsregisterauszug.pdf' }))
    await user.click(screen.getByRole('button', { name: 'Delete selected' }))

    expect(screen.getByText(/Delete 2 documents\? This cannot be undone\./)).toBeInTheDocument()
    expect(deleteDocumentMock).not.toHaveBeenCalled()
  })

  test('confirming deletes every chosen document and reports them together', async () => {
    const user = userEvent.setup()
    const onDeleted = vi.fn()
    render(<Harness documents={[FIRST, SECOND]} onDeleted={onDeleted} />)

    await user.click(screen.getByRole('checkbox', { name: 'Select Leistungsbeschreibung.pdf' }))
    await user.click(screen.getByRole('checkbox', { name: 'Select Handelsregisterauszug.pdf' }))
    await user.click(screen.getByRole('button', { name: 'Delete selected' }))
    await user.click(screen.getByRole('button', { name: 'Delete' }))

    await waitFor(() => expect(deleteDocumentMock).toHaveBeenCalledTimes(2))
    expect(deleteDocumentMock).toHaveBeenCalledWith(FIRST.id)
    expect(deleteDocumentMock).toHaveBeenCalledWith(SECOND.id)
    await waitFor(() => expect(onDeleted).toHaveBeenCalledWith([FIRST, SECOND]))
  })

  test('cancelling deletes nothing', async () => {
    const user = userEvent.setup()
    render(<Harness documents={[FIRST]} />)

    await user.click(screen.getByRole('checkbox', { name: 'Select Leistungsbeschreibung.pdf' }))
    await user.click(screen.getByRole('button', { name: 'Delete selected' }))
    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(deleteDocumentMock).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Delete selected' })).toBeInTheDocument()
  })

  test('a document a bid has claimed cannot be ticked', () => {
    render(<Harness documents={[IN_A_BID]} />)

    const row = screen.getByRole('row', { name: /Rahmenvereinbarung\.pdf/ })
    const box = within(row).getByRole('checkbox')

    expect(box).toBeDisabled()
  })

  test('a claimed document says on its face that it cannot be deleted', () => {
    render(<Harness documents={[IN_A_BID]} />)

    const row = screen.getByRole('row', { name: /Rahmenvereinbarung\.pdf/ })

    // Visible text, not a tooltip: a disabled box with a `title` tells a sighted user
    // nothing unless they happen to hover it.
    expect(within(row).getByText(/In 2 analyses — cannot be deleted/)).toBeInTheDocument()
  })

  test('the marker counts the analyses rather than saying "a bid"', () => {
    // A document may be used by several analyses at once since ADR-0103, so a constant
    // string would be wrong for all but one of them. Both branches in one render.
    render(<Harness documents={[IN_ONE_BID, IN_A_BID]} />)

    const one = screen.getByRole('row', { name: /Vergabeunterlagen\.pdf/ })
    const two = screen.getByRole('row', { name: /Rahmenvereinbarung\.pdf/ })

    expect(within(one).getByText(/In 1 analysis — cannot be deleted/)).toBeInTheDocument()
    expect(within(two).getByText(/In 2 analyses — cannot be deleted/)).toBeInTheDocument()
  })

  test('a document that can be deleted carries no such marker', () => {
    render(<Harness documents={[FIRST]} />)

    const row = screen.getByRole('row', { name: /Leistungsbeschreibung\.pdf/ })

    expect(within(row).queryByText(/cannot be deleted/)).not.toBeInTheDocument()
    expect(within(row).queryByText(/used by/i)).not.toBeInTheDocument()
  })

  test('the table says once why those documents are refused', () => {
    render(<Harness documents={[IN_A_BID]} />)

    expect(
      screen.getByText(/requirements cite its pages.*delete the analyses instead/i)
    ).toBeInTheDocument()
  })

  test('select all takes every deletable document and leaves the claimed one alone', async () => {
    const user = userEvent.setup()
    render(<Harness documents={[FIRST, IN_A_BID, SECOND]} />)

    await user.click(
      screen.getByRole('checkbox', { name: 'Select every document that can be deleted' })
    )

    expect(screen.getByText('2 documents selected')).toBeInTheDocument()
  })

  test('a refusal names the document and its reason, and the others still go', async () => {
    const user = userEvent.setup()
    const onDeleted = vi.fn()
    const { ApiError } = await import('@/lib/api-client')
    deleteDocumentMock.mockImplementation((id: string) =>
      id === SECOND.id
        ? Promise.reject(
            new ApiError({
              status: 409,
              statusText: 'Conflict',
              method: 'delete',
              url: `/documents/${id}`,
              body: { detail: 'This document is part of a bid that has already been started.' },
            })
          )
        : Promise.resolve(undefined)
    )
    render(<Harness documents={[FIRST, SECOND]} onDeleted={onDeleted} />)

    await user.click(
      screen.getByRole('checkbox', { name: 'Select every document that can be deleted' })
    )
    await user.click(screen.getByRole('button', { name: 'Delete selected' }))
    await user.click(screen.getByRole('button', { name: 'Delete' }))

    expect(await screen.findByText(/bid that has already been started/)).toBeInTheDocument()
    // Scoped to the notice: the name is also in its row, which still stands — the row was
    // refused, not deleted, and that is half of what this test is for.
    const refusal = screen.getByRole('alert')
    expect(within(refusal).getByText('Handelsregisterauszug.pdf')).toBeInTheDocument()
    expect(screen.getByRole('row', { name: /Handelsregisterauszug\.pdf/ })).toBeInTheDocument()
    await waitFor(() => expect(onDeleted).toHaveBeenCalledWith([FIRST]))
  })
})
