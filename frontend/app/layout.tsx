import type { Metadata } from 'next'
import { Geist, Geist_Mono } from 'next/font/google'
import './globals.css'

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
      <body>{children}</body>
    </html>
  )
}
