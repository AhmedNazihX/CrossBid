/**
 * S7.4 — the user guide's screenshots, captured from the same harness the tests use.
 *
 * `npm run guide:shots` from `frontend/`. It reuses `playwright.config.ts` entirely — the
 * same `next dev` server in dev auth mode, the same fake API at the browser's network edge,
 * the same 1440x900 viewport the artboards were drawn for — and changes only where the specs
 * live and where the output goes.
 *
 * **A separate config rather than a spec in `e2e/`**, because the two have different jobs. The
 * suite is a gate: it runs in CI on every push and must stay fast and deterministic. Capturing
 * images is neither — it writes files into `docs/`, and a CI run that rewrites eight PNGs on
 * every push would put binary churn in every diff. So the shots are opt-in and the gate is not.
 *
 * **The images are the real UI, and the data is fixture data.** That is stated in the guide
 * beside them rather than left for a reader to assume. What it buys is that anyone can
 * regenerate them with no database, no key and no money — and that a renamed field breaks the
 * capture at `tsc`, because `e2e/support/fixtures.ts` is typed from `lib/api.ts`. A screenshot
 * that has quietly gone stale is the failure mode a user guide has; this is the cheapest
 * defence against it.
 *
 * The eCertis cross-border card is **not** captured here. It is the one screen whose value is
 * that the evidence came back from a real register for a real criterion id, so the guide uses
 * a live capture for it (S7.4's decision, 2026-09-16).
 */
import { defineConfig } from '@playwright/test'

import base from './playwright.config'

export default defineConfig({
  ...base,
  testDir: './e2e-guide',
  outputDir: './test-results-guide',
  // One worker: the shots are written to fixed paths under docs/, and two workers racing to
  // create the same directory is a flake with no upside — there are eight of them.
  workers: 1,
  reporter: [['list']],
  use: { ...base.use, screenshot: 'off' },
})
