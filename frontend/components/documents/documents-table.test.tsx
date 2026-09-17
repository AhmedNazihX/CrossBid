/**
 * `DocumentsTable` — the per-document result of the injection guard (S2.3.1, S4.2.2, audit
 * finding M11).
 *
 * Why this was quietly wrong: the guard runs, withholds passages from the corpus, and the
 * API reports `flagged_chunk_count` "for a badge" — and until 2026-09-16 no component read
 * it. A document read *Ready* with nothing beside it whether zero passages were withheld or
 * nine, so a bidder wondering why a passage they could see was never cited had nothing on
 * the screen to tell them. The row polls the same object that carries the count, so the
 * only missing piece was a column.
 *
 * The rows here are `ready`, which means `usePolling` never fetches: the table renders from
 * the props alone and no network stub is needed.
 */
import { render, screen, within } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { documentFixture } from '@/e2e/support/fixtures'

import { DocumentsTable } from './documents-table'

const READ_IN_FULL = documentFixture({
  id: '33333333-3333-4333-8333-333333333331',
  name: 'Leistungsbeschreibung.pdf',
})

const THREE_WITHHELD = documentFixture({
  id: '33333333-3333-4333-8333-333333333332',
  name: 'Bewerbungsbedingungen.pdf',
  flagged_chunks: [4, 9, 10],
  flagged_chunk_count: 3,
})

const ONE_WITHHELD = documentFixture({
  id: '33333333-3333-4333-8333-333333333334',
  name: 'Anlage_7.pdf',
  flagged_chunks: [2],
  flagged_chunk_count: 1,
})

const STILL_READING = documentFixture({
  id: '33333333-3333-4333-8333-333333333333',
  name: 'Vertragsentwurf.pdf',
  status: 'uploaded',
  pages: 0,
})

describe('DocumentsTable — withheld passages', () => {
  test('has a column for them', () => {
    render(
      <DocumentsTable
        documents={[READ_IN_FULL]}
        onDocumentChange={vi.fn()}
        selectedIds={new Set()}
        onSelectedChange={vi.fn()}
        onSelectAll={vi.fn()}
      />
    )

    expect(screen.getByRole('columnheader', { name: 'Withheld' })).toBeInTheDocument()
  })

  test('a ready document with withheld passages says how many, in words not colour', () => {
    render(
      <DocumentsTable
        documents={[THREE_WITHHELD]}
        onDocumentChange={vi.fn()}
        selectedIds={new Set()}
        onSelectedChange={vi.fn()}
        onSelectAll={vi.fn()}
      />
    )

    const row = screen.getByRole('row', { name: /Bewerbungsbedingungen\.pdf/ })

    expect(within(row).getByText('3 passages withheld')).toBeInTheDocument()
  })

  test('one passage is singular', () => {
    render(
      <DocumentsTable
        documents={[ONE_WITHHELD]}
        onDocumentChange={vi.fn()}
        selectedIds={new Set()}
        onSelectedChange={vi.fn()}
        onSelectAll={vi.fn()}
      />
    )

    expect(screen.getByText('1 passage withheld')).toBeInTheDocument()
  })

  test('a ready document with none reads 0, and one still being read reads a dash', () => {
    render(
      <DocumentsTable
        documents={[READ_IN_FULL, STILL_READING]}
        onDocumentChange={vi.fn()}
        selectedIds={new Set()}
        onSelectedChange={vi.fn()}
        onSelectAll={vi.fn()}
      />
    )

    const ready = screen.getByRole('row', { name: /Leistungsbeschreibung\.pdf/ })
    const reading = screen.getByRole('row', { name: /Vertragsentwurf\.pdf/ })
    const readyCells = within(ready).getAllByRole('cell')
    const readingCells = within(reading).getAllByRole('cell')

    // Withheld is the sixth cell — the selection box, Type, Status, Pages, Unread pages,
    // Withheld. (The name is a rowheader, not a cell.) Indexing from the end read the wrong
    // column twice while the trailing action column came and went, so it is counted from the
    // front now.
    const WITHHELD = 5
    expect(readyCells[WITHHELD]).toHaveTextContent(/^0$/)
    expect(readingCells[WITHHELD]).toHaveTextContent(/^—$/)
  })

  test('the badge explains what withheld means, for a reader as well as a pointer', () => {
    render(
      <DocumentsTable
        documents={[THREE_WITHHELD]}
        onDocumentChange={vi.fn()}
        selectedIds={new Set()}
        onSelectedChange={vi.fn()}
        onSelectAll={vi.fn()}
      />
    )

    const badge = screen.getByText('3 passages withheld')

    expect(badge.closest('[title]')).toHaveAttribute('title', expect.stringMatching(/agent/))
    expect(screen.getByText(/were not given to the agent/)).toBeInTheDocument()
  })
})
