/**
 * S7.4 — the one screenshot taken from live services rather than from fixtures.
 *
 *   npx playwright test --config playwright.live.config.ts
 *
 * Needs a real stack: an API on `E2E_LIVE_API` serving a database that
 * `scripts/index_pack.py fr --with-evidence` and `scripts/run_full_bid.py fr` have populated,
 * and a Next server on `E2E_LIVE_BASE` built against that API in dev auth mode.
 *
 * **Why this one is live when the other seven are not.** The rest of the guide's images show
 * the interface doing things, and fixture data shows that faithfully while staying free and
 * reproducible. This one is a claim about the outside world: that a French buyer's ESPD
 * criterion resolves, through the EU's own register, to the German document a German bidder
 * would actually produce. A fixture asserting that would be a picture of our own belief. The
 * run behind it is committed at `backend/tests/fixtures/bids/fr.cross-border.json` — 30 rows
 * carried a criterion id and 29 resolved.
 *
 * It is **not** part of `npm run test:e2e` and not in CI: it needs services that only exist
 * while somebody is standing them up, and a gate that depends on that is a flaky gate.
 */
import path from 'node:path'

import { expect, test } from '@playwright/test'

const BID = process.env.E2E_LIVE_BID ?? ''
const SHOTS = path.resolve(__dirname, '../../docs/user-guide/img')

test('08 — a French criterion resolved to German evidence', async ({ page }) => {
  test.skip(BID === '', 'set E2E_LIVE_BID to the bid to photograph')

  await page.goto(`/bids/${BID}`)

  // The card announces itself as `eCertis · <criterion>`; the <b> sits two levels inside the
  // card's own box, so the element shot is the card and nothing else. A full-page shot of
  // this bid is 147 requirements and roughly 36 000 pixels tall — unusable in a guide.
  // The card lives in the detail panel, which only exists once a row is selected — so the
  // shot has to open one. This row came from the buyer's published DUME, which is what gives
  // it a canonical EU criterion id and therefore an eCertis lookup at all.
  const row = page.getByRole('button', { name: /Chiffre\(s\) d.affaires annuel général/i })
  await expect(row.first()).toBeVisible({ timeout: 30_000 })
  await row.first().click()

  // The heading is a <b> inside the card's inner div, so two levels up is the card's own box.
  // It resolves only once a row is open, which is why the click above comes first.
  // `:visible` matters: every row renders its own detail panel and 29 of them are in the
  // DOM at once, collapsed. Without it `.first()` picks a hidden card from another row.
  const heading = page
    .locator('b:visible')
    .filter({ hasText: /^eCertis · / })
    .first()
  await expect(heading).toBeVisible({ timeout: 15_000 })
  const card = heading.locator('xpath=../..')
  await expect(card).toContainText(/Bescheinigung|Bundeszentralregister|Führungszeugnis|AVPQ/i)
  await card.scrollIntoViewIfNeeded()
  await card.screenshot({ path: path.join(SHOTS, '08-ecertis-live.png') })

  // Only the card is captured, not the screen around it. The eval harness seeds documents
  // with synthetic storage keys and uploads nothing, so the source panel beside this row
  // correctly reports "the document could not be opened" — true of this database and untrue
  // of the product, which is exactly the kind of thing a guide screenshot must not imply.
})
