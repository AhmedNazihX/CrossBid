/**
 * The 404 page (S7.7; M8 of the 2026-09-15 audit).
 *
 * Until `app/not-found.tsx` existed, a mistyped URL showed Next's unbranded "404 / This page
 * could not be found" — the one screen nobody had written, because nothing ever asked for a
 * page that did not exist. It was possible for the simplest reason a defect can have: the
 * framework supplies a default, so the absence of our own was invisible until somebody typed
 * a wrong address. This asserts the status is still a 404 (a branded page that answers 200
 * would be worse: it would look right to a person and wrong to every crawler and monitor),
 * that it is ours, and that the way back is the dashboard.
 */
import { expect, test } from './support/test'

test('a URL that matches no route gets CrossBid’s own 404, not the framework’s', async ({
  page,
}) => {
  const response = await page.goto('/there-is-no-page-at-this-address')
  expect(response?.status()).toBe(404)

  await expect(
    page.getByRole('heading', { level: 1, name: 'There is no page at this address' })
  ).toBeVisible()
  await expect(page.getByRole('link', { name: 'Go to the dashboard' })).toHaveAttribute(
    'href',
    '/dashboard'
  )
  await expect(page.getByRole('link', { name: 'CrossBid — home' })).toBeVisible()
  await expect(page.getByText('This page could not be found')).toHaveCount(0)
})
