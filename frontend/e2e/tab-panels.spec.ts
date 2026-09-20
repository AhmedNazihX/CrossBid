/**
 * The workspace's tab panels have names — finding L3 of the 2026-09-15 audit.
 *
 * `components/ui/tabs.tsx` exported a `tabId` helper that generated each tab's `id` from a
 * prefix it made privately with `useId`, so **no caller could name that id**: the seven
 * panels of the two workspace layouts carried `role="tabpanel"` and an `id` and nothing
 * pointing back at the tab that controls them. A screen-reader user moving into a panel was
 * told "tab panel" and nothing else — which section they had just opened was exactly the
 * thing not said. (`components/matrix/requirement-list.tsx` was already fine: one panel
 * serves all its tabs, so it names itself with `aria-label`.)
 *
 * The fix (ADR-0096) derives the tab's id from the panel's, which the caller already owns
 * and passes in as `panelId`, so a panel can say `aria-labelledby={tabId(...)}` with no new
 * prop and no shared secret.
 *
 * Both layouts used to be checked, because they are two components since ADR-0086 and a name
 * added to one is not a name added to the other. **Since ADR-0104 the desktop has no tab set
 * at all** — Ask moved above the matrix, the source became a drawer, and the rail holds the
 * verdict alone — so the phone is the only layout with tab panels left to name, and this file
 * is now about the phone. The desktop's equivalent contract (the drawer is a labelled dialog
 * that Escape closes) is asserted in `bid-workspace.spec.ts`.
 *
 * The assertion is Playwright's accessible-name lookup rather than a check for the attribute:
 * an `aria-labelledby` pointing at an id that does not exist is the failure this defect would
 * most plausibly come back as, and it leaves the attribute present and the name empty.
 */
import { awaitingReviewBidFixture, BID_ID } from './support/fixtures'
import { expect, test } from './support/test'

/** `PHONE_TABS` in `workspace-state.ts`. */
const PHONE_PANELS = ['Matrix', 'Source', 'Verdict', 'Ask'] as const
/** Far enough out that the source panel does not refresh the URL mid-test. */
const SIGNED_URL_TTL_MS = 10 * 60 * 1_000

test.describe('Workspace tab panels', () => {
  test.beforeEach(async ({ api, apiOrigin, page }) => {
    const bid = awaitingReviewBidFixture()
    api.on('GET', `/bids/${BID_ID}`, { status: 200, json: bid })
    api.on('GET', `/bids/${BID_ID}/feedback`, { status: 200, json: { feedback: [] } })
    api.on('GET', '/documents', { status: 200, json: { documents: [] } })
    const sourcePage = `${apiOrigin}/e2e/source-page`
    api.on('GET', /^\/documents\/[^/]+\/url$/, () => ({
      status: 200,
      json: {
        url: sourcePage,
        expires_at: new Date(Date.now() + SIGNED_URL_TTL_MS).toISOString(),
      },
    }))
    api.on('GET', '/e2e/source-page', {
      status: 200,
      contentType: 'text/html',
      body: '<!doctype html><title>e2e source page</title><p>The PDF viewer would be here.</p>',
    })

    await page.goto(`/bids/${BID_ID}`)
    await expect(page.getByRole('heading', { level: 1, name: bid.title })).toBeVisible()
  })

  test.describe('the phone layout', () => {
    test.use({ viewport: { width: 390, height: 844 } })

    test('each panel is named by the tab that opened it', async ({ page }) => {
      for (const label of PHONE_PANELS) {
        await page.getByRole('tab', { name: label }).click()
        // Only the open panel is in the accessibility tree — the rest carry `hidden` or are
        // unmounted — so this is the panel the tab just revealed, asked for by the name it
        // should now have.
        await expect(page.getByRole('tabpanel', { name: label })).toBeVisible()
      }
    })
  })

  test('the desktop has no tab set: the rail is the verdict alone (ADR-0104)', async ({
    page,
  }) => {
    await expect(page.getByRole('tablist', { name: 'Workspace panels' })).toHaveCount(0)
    await expect(page.locator('#verdict')).toBeVisible()
  })
})
