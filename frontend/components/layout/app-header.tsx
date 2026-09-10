import Link from 'next/link'

import { MainNav } from './main-nav'
import { MobileNav } from './mobile-nav'

/**
 * The shell's banner: wordmark, navigation, and the seam where the account
 * control will sit.
 *
 * Sign-in, the signed-in email and sign-out belong to S4.1.1; until it lands the
 * shell shows no account state at all rather than a link that goes nowhere
 * (docs/project-plan.md, S4.1.2: "login link appears with S4.1.1").
 */
export function AppHeader() {
  return (
    <header className="bg-background/95 supports-backdrop-filter:backdrop-blur sticky top-0 z-40 border-b">
      <div className="mx-auto flex h-14 w-full max-w-5xl items-center justify-between gap-4 px-4">
        <Link
          href="/dashboard"
          className="focus-visible:ring-ring rounded-lg text-base font-semibold tracking-tight focus-visible:ring-3 focus-visible:outline-none"
        >
          Crossbid
        </Link>

        <div className="flex items-center gap-2">
          <MainNav />
          {/* S4.1.1 mounts the account menu (signed-in email, sign out) here. */}
          <MobileNav />
        </div>
      </div>
    </header>
  )
}
