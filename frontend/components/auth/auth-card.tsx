/**
 * The chrome both auth screens sit in: lockup, card, and the advisory-only footnote.
 *
 * Extracted when `new-password-card.tsx` arrived and needed the same frame. It has no
 * artboard of its own — it is the one ADR-0034 built for sign-in, now shared rather than
 * copied, so the two screens cannot drift apart by a padding value.
 */
import Image from 'next/image'
import Link from 'next/link'
import type { ReactNode } from 'react'

export function AuthCard({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center bg-surface-canvas px-4 py-12">
      <div className="flex w-full max-w-[400px] flex-col gap-6">
        <Link
          href="/"
          className="inline-flex min-h-11 items-center self-center rounded-md"
          aria-label="CrossBid — home"
        >
          <Image
            src="/logo-lockup.svg"
            alt="CrossBid"
            width={124}
            height={30}
            priority
            className="block h-[30px] w-auto"
          />
        </Link>
        <div className="flex flex-col gap-5 rounded-[14px] border border-border-default bg-surface-card p-7 shadow-xs">
          {children}
        </div>
        <p className="m-0 text-center [font:var(--type-body-sm)] text-text-muted">
          Crossbid is advisory: it never submits a bid for you.
        </p>
      </div>
    </main>
  )
}
