/**
 * The `test` every spec imports: Playwright's, plus two guards that run on every journey.
 *
 * - `api` installs `FakeApi` before the page loads and, when the test is over, fails it if
 *   the page called anything nobody stubbed. That is what keeps a run from ever touching a
 *   real API, and what makes a screen that quietly starts fetching something new visible.
 * - `consoleErrors` collects `console.error` and uncaught exceptions and fails the test on
 *   any. Eighteen thousand lines had no test at all when the 2026-09-15 audit ran; a page
 *   that renders and logs an error is the cheapest whole class of defect to refuse. One line
 *   is not counted: Chrome's own "Failed to load resource: …" for an outcome the test itself
 *   chose — a status the fake served, a stub it aborted (`net::ERR_FAILED`), or the document
 *   the test navigated to (the 404 page's whole point). A missing chunk, a broken image or a
 *   React error on the app's origin is still an error.
 *
 * The shell probes `GET /dev/settings` on every screen (`lib/use-developer-access.ts`); the
 * `api` fixture answers it 403, which is what a bidder who is not on `DEVELOPER_EMAILS`
 * gets and hides the developer console. A spec about that console overrides it.
 *
 * Both are `auto`, so a spec gets them without naming them. `apiOrigin` is an option set in
 * `playwright.config.ts` (`E2E_API_URL`) and must equal the `NEXT_PUBLIC_API_URL` the server
 * under test was started with — the fake tells API calls from the app's own by origin.
 */
import { test as base, expect, type ConsoleMessage, type Page } from '@playwright/test'

import { type FakeApi, installFakeApi } from './fake-api'

export interface E2EOptions {
  readonly apiOrigin: string
}

interface E2EFixtures {
  readonly api: FakeApi
  readonly consoleErrors: readonly string[]
}

export const test = base.extend<E2EOptions & E2EFixtures>({
  apiOrigin: ['http://127.0.0.1:8100', { option: true }],

  api: [
    async ({ page, baseURL, apiOrigin }, use) => {
      if (baseURL === undefined) {
        throw new Error(
          'playwright.config.ts must set use.baseURL: the fake API tells the app’s own requests from API calls by origin.'
        )
      }
      const api = await installFakeApi(page, { apiOrigin, appOrigin: new URL(baseURL).origin })
      api.on('GET', '/dev/settings', {
        status: 403,
        json: { detail: 'The developer console is for the accounts on DEVELOPER_EMAILS.' },
      })
      await use(api)
      expect(
        api.unexpected,
        'API calls the page made that no test stubbed. Register each with api.on(), and check that E2E_API_URL matches the NEXT_PUBLIC_API_URL the server was started with.'
      ).toEqual([])
    },
    { auto: true },
  ],

  consoleErrors: [
    async ({ page, apiOrigin }, use) => {
      // A collector: appended to by the page's events while the test runs, read at the end.
      const errors: string[] = []
      page.on('console', (message) => {
        if (message.type() !== 'error' || isChosenOutcome(message, page, apiOrigin)) return
        errors.push(`console.error: ${message.text()}`)
      })
      page.on('pageerror', (error) => {
        errors.push(`uncaught: ${error.message}`)
      })
      await use(errors)
      expect(errors, 'the page logged an error while the journey ran').toEqual([])
    },
    { auto: true },
  ],
})

export { expect }

const RESOURCE_OUTCOME_LINE =
  /^Failed to load resource: (the server responded with a status of \d{3}|net::ERR_FAILED)/

/**
 * Chrome writes a `console.error` for every response with a 4xx/5xx status, and one for a
 * request that failed outright. When that outcome came from the fake (the test chose the
 * status, or aborted the stub) or is the document itself (the test navigated there and
 * asserts the status), the line reports the test's own decision back to it. Everything else
 * on the app's origin — a chunk, an image, a font — is real.
 */
function isChosenOutcome(message: ConsoleMessage, page: Page, apiOrigin: string): boolean {
  if (!RESOURCE_OUTCOME_LINE.test(message.text())) return false
  const url = message.location().url
  if (url === page.url()) return true
  try {
    return new URL(url).origin === apiOrigin
  } catch {
    return false
  }
}
