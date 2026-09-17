/**
 * The notice a bid gets when Ask cannot read its documents (2026-09-17).
 *
 * A bidder asked the chat who the buyer was and was told nothing could be found in the tender
 * documents, with a complete 144-row matrix on screen citing pages of the same PDF. The bid had
 * been analysed the day before `parse_docs` started writing `tender_chunks`, so its pack was
 * parsed and extracted from without a searchable copy being kept (ADR-0098).
 *
 * Nothing on the workspace said so. *Problems flagged* read **0**, correctly — nothing had
 * failed, the step had simply never existed — so the only way to discover it was to ask the
 * agent a question it could not answer. This is the fact stated where the bid is, rather than
 * left to be inferred from a refusal.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'

import { UnsearchablePack } from './unsearchable-pack'

const document = (name: string, searchable: boolean) => ({
  id: `id-${name}`,
  name,
  pages: 10,
  unread_pages: [],
  searchable,
})

describe('UnsearchablePack', () => {
  test('says nothing when every document can be searched', () => {
    const { container } = render(
      <UnsearchablePack documents={[document('rc.pdf', true), document('cctp.pdf', true)]} />
    )

    expect(container).toBeEmptyDOMElement()
  })

  test('says nothing when the bid has no documents at all', () => {
    // A bid still queued has none. "Ask cannot read your pack" would be alarming and wrong.
    const { container } = render(<UnsearchablePack documents={[]} />)

    expect(container).toBeEmptyDOMElement()
  })

  test('names the whole pack when none of it can be searched', () => {
    render(
      <UnsearchablePack documents={[document('rc.pdf', false), document('cctp.pdf', false)]} />
    )

    const notice = screen.getByRole('status')
    expect(notice).toHaveTextContent(/ask cannot read/i)
    // The two things a bidder needs: that the matrix is unaffected, and what to do.
    expect(notice).toHaveTextContent(/matrix/i)
    expect(notice).toHaveTextContent(/index/i)
  })

  test('counts them when only some cannot be searched', () => {
    render(
      <UnsearchablePack
        documents={[
          document('rc.pdf', true),
          document('cctp.pdf', false),
          document('dume.xml', false),
        ]}
      />
    )

    expect(screen.getByRole('status')).toHaveTextContent(/2 of 3/i)
  })
})
