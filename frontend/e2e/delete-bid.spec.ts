/**
 * Deleting a tender analysis, from the two places it is offered.
 *
 * The delete is asymmetric and the confirmation has to say so: the analysis goes, the bidder's
 * uploaded documents stay and become deletable again (the server detaches them before the
 * delete, which is what releases the lock), and the spend stays in the cost console.
 *
 * **The reachability assertion is not decoration.** `DeleteSelected` carries a warning earned
 * the hard way: the first delete control this repository had was a table's last column, and
 * `DataTable` scrolls horizontally whenever its content outgrows the window — at 1100 px that
 * control sat 106 px past the right edge, reachable only by a bidder who thought to drag the
 * table sideways. This one is a last column too, so its box is measured against the viewport
 * at the same width rather than assumed.
 */
import { awaitingReviewBidFixture, BID_ID } from './support/fixtures'
import { expect, test } from './support/test'

/** The width the documents table's control was measured unreachable at. */
const NARROW = { width: 1100, height: 900 }

const bidSummary = {
  id: BID_ID,
  title: '618320-2026',
  ted_publication_number: '618320-2026',
  source_language: 'fr',
  status: 'complete',
  updated_at: '2026-09-14T11:53:00Z',
  open_items: 0,
  deadline: null,
}

test.describe('Deleting a tender analysis', () => {
  test('the list offers it, asks first, and the control is reachable at 1100px', async ({
    api,
    page,
  }) => {
    await page.setViewportSize(NARROW)
    api.on('GET', '/bids', { status: 200, json: { bids: [bidSummary], next_cursor: null } })
    let deleted = false
    api.on('DELETE', `/bids/${BID_ID}`, () => {
      deleted = true
      return { status: 204 }
    })

    await page.goto('/bids')
    const control = page.getByRole('button', { name: 'Delete analysis' })
    await expect(control).toBeVisible()

    // Reachable without dragging the table sideways: the whole control inside the viewport.
    const box = await control.boundingBox()
    if (box === null) throw new Error('the control has no box, so nothing was measured')
    expect(
      box.x + box.width,
      `the control ends at x=${Math.round(box.x + box.width)}`
    ).toBeLessThanOrEqual(NARROW.width)

    await control.click()
    const question = page.getByRole('alertdialog')
    await expect(question).toContainText('618320-2026')
    await expect(question).toContainText(/kept/i)
    expect(deleted, 'asked, not done').toBe(false)

    await page.getByRole('button', { name: 'Delete', exact: true }).click()
    await expect(page.getByRole('button', { name: 'Delete analysis' })).toHaveCount(0)
    expect(deleted).toBe(true)
  })

  test('the workspace offers it and leaves for the list once it is gone', async ({
    api,
    page,
  }) => {
    api.on('GET', `/bids/${BID_ID}`, { status: 200, json: awaitingReviewBidFixture() })
    api.on('GET', `/bids/${BID_ID}/feedback`, { status: 200, json: { feedback: [] } })
    api.on('GET', '/documents', { status: 200, json: { documents: [] } })
    api.on('GET', '/bids', { status: 200, json: { bids: [], next_cursor: null } })
    api.on('DELETE', `/bids/${BID_ID}`, { status: 204 })
    // The source panel opens the first document as soon as the workspace renders.
    api.on('GET', /^\/documents\/[^/]+\/url$/, () => ({
      status: 200,
      json: { url: 'about:blank', expires_at: new Date(Date.now() + 600_000).toISOString() },
    }))

    await page.goto(`/bids/${BID_ID}`)
    await page.getByRole('button', { name: 'Delete analysis' }).click()
    await page.getByRole('button', { name: 'Delete', exact: true }).click()

    // The workspace polls the bid it has just deleted, so leaving is part of the delete.
    await expect(page).toHaveURL(/\/bids$/)
  })

  test('a run still going is refused, in the words the server used', async ({ api, page }) => {
    api.on('GET', '/bids', {
      status: 200,
      json: { bids: [{ ...bidSummary, status: 'checking' }], next_cursor: null },
    })
    api.on('DELETE', `/bids/${BID_ID}`, {
      status: 409,
      json: { detail: 'This analysis is still running. Wait for it to finish or fail.' },
    })

    await page.goto('/bids')
    await page.getByRole('button', { name: 'Delete analysis' }).click()
    await page.getByRole('button', { name: 'Delete', exact: true }).click()

    // Scoped to the question: the page carries other alerts, and "an alert exists" is not
    // the claim — the server's own sentence reaching this control is.
    await expect(page.getByRole('alertdialog').getByRole('alert')).toContainText(
      /still running/i
    )
    await expect(page.getByRole('button', { name: 'Delete', exact: true })).toBeVisible()
  })
})
