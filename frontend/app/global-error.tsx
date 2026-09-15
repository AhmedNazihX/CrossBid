'use client'

/**
 * The last boundary: what renders when the root layout itself throws (M8 of the 2026-09-15
 * audit).
 *
 * Next mounts this *instead of* `app/layout.tsx`, so nothing that layout provides exists
 * here — no `<html>`, no `<body>`, no `SessionProvider`, no font variables and no imported
 * stylesheet. The file therefore supplies its own document, imports the token sheet, and
 * loads Geist again so the screen is the app's and not the browser's default serif. It uses a
 * plain anchor for the way back rather than `Link`: the router tree `Link` would navigate
 * within is the thing that has just failed, and a full document load is the honest recovery.
 *
 * The frame is `AuthCard`'s by measure — canvas, 400 px column, 14 px card, footnote — written
 * out once here rather than imported: `AuthCard` wraps its lockup in `next/link`, whose router
 * is what has just failed, and a boundary that replaces the document should lean on nothing
 * but pure primitives (`Button`, `Notice`, `next/image`). Same wording rules as `error.tsx`:
 * what happened and what to do, never the raw error. The CSP of ADR-0036 is untouched — no
 * inline script, and inline style is already allowed.
 *
 * In development Next's own overlay takes this screen's place; it is a production surface.
 */
import { Geist } from 'next/font/google'
import Image from 'next/image'
import './globals.css'

import { Button } from '@/components/ui/button'
import { Notice } from '@/components/ui/notice'

const geistSans = Geist({
  variable: '--font-geist-sans',
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
})

interface GlobalErrorProps {
  readonly error: Error & { readonly digest?: string }
  readonly reset: () => void
}

export default function GlobalError({ reset }: GlobalErrorProps) {
  return (
    <html lang="en" className={geistSans.variable}>
      <body>
        <main className="flex min-h-dvh flex-col items-center justify-center bg-surface-canvas px-4 py-12">
          <div className="flex w-full max-w-[400px] flex-col gap-6">
            <Image
              src="/logo-lockup.svg"
              alt="CrossBid"
              width={124}
              height={30}
              priority
              className="block h-[30px] w-auto self-center"
            />
            <div className="flex flex-col gap-5 rounded-[14px] border border-border-default bg-surface-card p-7 shadow-xs">
              <h1 className="m-0 text-[length:var(--text-lg)] font-semibold text-text-primary">
                CrossBid could not be shown
              </h1>
              <Notice tone="danger" title="Something went wrong">
                The app hit an error before it could draw anything. Trying again reloads it; if
                that fails too, the dashboard link below starts from a clean page.
              </Notice>
              <div className="flex flex-col gap-3">
                <Button fullWidth onClick={reset}>
                  Try again
                </Button>
                <Button asChild variant="secondary" fullWidth>
                  <a href="/dashboard">Back to the dashboard</a>
                </Button>
              </div>
            </div>
            <p className="m-0 text-center [font:var(--type-body-sm)] text-text-muted">
              Crossbid is advisory: it never submits a bid for you.
            </p>
          </div>
        </main>
      </body>
    </html>
  )
}
