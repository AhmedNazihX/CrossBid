import { AppFooter } from '@/components/layout/app-footer'
import { AppHeader } from '@/components/layout/app-header'
import { SkipToContent } from '@/components/layout/skip-to-content'
import { MAIN_CONTENT_ID } from '@/components/layout/nav-items'

/**
 * The authenticated shell (story S4.1.2).
 *
 * Every route in the `(app)` group renders inside it, so navigation and the
 * advisory-only notice are identical on every page. The route group adds no URL
 * segment: `app/(app)/dashboard/page.tsx` is `/dashboard`.
 *
 * There is no session check here yet — the redirect for a signed-out visitor is
 * S4.1.1, and this story deliberately does not build auth.
 */
export default function AppLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <div className="flex min-h-screen flex-col">
      <SkipToContent />
      <AppHeader />
      <main
        id={MAIN_CONTENT_ID}
        className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 px-4 py-8"
      >
        {children}
      </main>
      <AppFooter />
    </div>
  )
}
