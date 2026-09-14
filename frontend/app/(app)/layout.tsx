import { RequireSession } from '@/components/auth/require-session'
import { MobileHeader } from '@/components/layout/mobile-header'
import { MAIN_CONTENT_ID } from '@/components/layout/nav-items'
import { Sidebar } from '@/components/layout/sidebar'
import { SkipToContent } from '@/components/layout/skip-to-content'

/**
 * The authenticated shell — `ui_kits/app/Shell.jsx` (ADR-0014): a 260 px canvas sidebar
 * and a single white content frame (1 px border, 14 px radius, 32 px padding,
 * `--shadow-xs`) inset 28 px from the top and right. Below 900 px the sidebar gives way to
 * `MobileHeader` and the content sits on the canvas with 16 px gutters, as
 * `WorkspacePhone.dc.html` draws it.
 *
 * Every route in the `(app)` group renders inside it. The route group adds no URL segment:
 * `app/(app)/dashboard/page.tsx` is `/dashboard`. `RequireSession` (S4.1.1) is what stands
 * in front of all of them: a signed-out visitor is sent to `/login` carrying the path they
 * asked for, and on the dev bridge it renders straight through.
 */
export default function AppLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <RequireSession>
      <div className="flex min-h-screen flex-col bg-surface-canvas shell:flex-row">
        <SkipToContent />
        <Sidebar />
        <MobileHeader />
        <main id={MAIN_CONTENT_ID} className="min-w-0 flex-1 shell:py-7 shell:pr-7">
          <div className="flex min-h-full flex-col px-4 py-5 shell:min-h-[calc(100vh-56px)] shell:rounded-[14px] shell:border shell:border-border-default shell:bg-surface-card shell:p-8 shell:shadow-xs">
            {children}
          </div>
        </main>
      </div>
    </RequireSession>
  )
}
