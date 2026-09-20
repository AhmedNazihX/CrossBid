/**
 * The dashboard renders its data with a clean console (S7.7).
 *
 * The cheapest guard that catches a whole class: a screen that paints and logs an error —
 * a hydration mismatch, a key warning, an uncaught exception in an effect, a chunk that
 * failed to load — looks fine in a screenshot and is broken in a way the next change makes
 * worse. Eighteen thousand lines had no test at all when the 2026-09-15 audit ran, so no
 * page had ever been loaded by anything that read the console. The guard itself is the
 * `consoleErrors` fixture and runs on every spec; this test gives it the screen with the most
 * on it — metrics, the tenders table, a verdict chip, a deadline on the buyer's clock — and
 * asserts the data actually arrived, so an empty console is not the console of an empty
 * page.
 */
import { bidSummaryFixture } from './support/fixtures'
import { expect, test } from './support/test'

test('the dashboard lists the company’s bids without logging an error', async ({
  api,
  page,
  consoleErrors,
}) => {
  const parked = bidSummaryFixture()
  const decided = bidSummaryFixture({
    id: '66666666-6666-4666-8666-666666666666',
    ted_publication_number: '618320-2026',
    title: 'Maintenance des systèmes d’information',
    buyer: 'Ministère de l’Intérieur',
    source_language: 'fr',
    deadline: null,
    deadline_utc_offset_minutes: null,
    status: 'complete',
    decision: 'go',
    open_items: 0,
  })
  api.on('GET', '/bids', { status: 200, json: { bids: [parked, decided] } })

  await page.goto('/dashboard')

  await expect(page.getByRole('heading', { level: 1, name: 'Dashboard' })).toBeVisible()
  await expect(
    page.getByRole('heading', { level: 2, name: 'Tenders by deadline' })
  ).toBeVisible()
  const table = page.getByRole('table')
  await expect(table).toBeVisible()
  await expect(table.getByText(parked.title)).toBeVisible()
  await expect(table.getByText(decided.title)).toBeVisible()

  expect(consoleErrors).toEqual([])
})

/**
 * The shell's logo leads to the landing page (ADR-0109).
 *
 * It led to `/dashboard`, which is the usual convention for a signed-in app — the logo is the
 * app's own home. This reverses that on purpose, so the test asserts the **destination** and
 * not only that the logo is a link: the accessible name alone passed against the old target
 * too, and a name is not where a click goes.
 *
 * Measured red against `href="/dashboard"`: the URL after the click is the dashboard's.
 */
test('the logo leads back to the landing page', async ({ api, page }) => {
  api.on('GET', '/bids', { status: 200, json: { bids: [] } })

  await page.goto('/dashboard')
  const logo = page.getByRole('link', { name: 'CrossBid — home' })
  await expect(logo).toBeVisible()

  await logo.click()

  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByRole('heading', { level: 1 })).toContainText(/Know if you can win/i)
})
