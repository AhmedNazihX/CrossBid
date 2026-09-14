import type { Metadata } from 'next'
import { Geist, Geist_Mono } from 'next/font/google'
import './globals.css'

import { SessionProvider } from '@/components/auth/session-provider'

/**
 * Rendered per request, for the nonce (ADR-0036).
 *
 * `middleware.ts` mints a fresh CSP nonce per request and Next stamps its own inline
 * hydration scripts with it — but only while it is *rendering* that request. A
 * prerendered page carries whatever nonce existed at build time, which matches no header
 * any visitor will ever receive, so every one of its scripts is blocked and the page is
 * dead. Measured before this line existed: 17 script tags, none of them nonced.
 *
 * Declared on the root layout so it reaches every route, because the policy does: the
 * session is in `localStorage`, which is scoped to the origin rather than to a page.
 */
export const dynamic = 'force-dynamic'

/**
 * Geist and Geist Mono, the design system's single family (`tokens/fonts.css` lists the
 * same weights: 400/500/600/700 sans, 400/500 mono). `next/font` self-hosts them, so the
 * page never fetches from Google at run time; `globals.css` reads the two variables.
 */
const geistSans = Geist({
  variable: '--font-geist-sans',
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
})

const geistMono = Geist_Mono({
  variable: '--font-geist-mono',
  subsets: ['latin'],
  weight: ['400', '500'],
})

export const metadata: Metadata = {
  title: 'CrossBid',
  description:
    'Go / no-go for cross-border EU tenders. Advisory by design — CrossBid never submits a bid.',
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable}`}>
      <body>
        <SessionProvider>{children}</SessionProvider>
      </body>
    </html>
  )
}
