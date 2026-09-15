import { RequireCompany } from '@/components/auth/require-company'
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
 * asked for, and on the dev bridge it renders straight through. `RequireCompany` (S4.2.1)
 * then sends an account with no company to the form that creates one.
 *
 * **The guards sit inside the content frame, not around the shell.** They used to wrap this
 * whole tree, so while the session was being read out of `localStorage` — every full load of
 * every protected route — the only thing on screen was their centred "Loading…" on an empty
 * viewport: no sidebar, no header (M7 of the 2026-09-15 audit, caught in three screenshots).
 * The chrome carries nothing that needs a session to be shown — the nav is a constant list,
 * the account block renders nothing until `signedIn`, and the developer probe in `NavGroups`
 * waits for the session — so it can paint first, and only the frame has to wait. The
 * alternative, a `loading.tsx`, is the wrong tool: that is Suspense for the server render,
 * and this wait is client state.
 */
export default function AppLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <div className="flex min-h-screen flex-col bg-surface-canvas shell:flex-row">
      <SkipToContent />
      <Sidebar />
      <MobileHeader />
      <main id={MAIN_CONTENT_ID} className="min-w-0 flex-1 shell:py-7 shell:pr-7">
        <div className="flex min-h-full flex-col px-4 py-5 shell:min-h-[calc(100vh-56px)] shell:rounded-[14px] shell:border shell:border-border-default shell:bg-surface-card shell:p-8 shell:shadow-xs">
          <RequireSession>
            <RequireCompany>{children}</RequireCompany>
          </RequireSession>
        </div>
      </main>
    </div>
  )
}
