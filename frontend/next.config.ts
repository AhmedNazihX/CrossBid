import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  // Emits .next/standalone with a self-contained server.js, so the Docker
  // runtime stage needs neither node_modules nor the npm lockfile.
  output: 'standalone',

  // The API is a separate process on a separate origin (see docs/project-plan.md
  // -> "Frontend <-> backend boundary"). Nothing is proxied through Next.js.
  reactStrictMode: true,

  /**
   * The security headers that are the same on every response (ADR-0036).
   *
   * The Content-Security-Policy is *not* here: it carries a per-request nonce and so has
   * to be built per request, which is what `middleware.ts` does. These are the constant
   * ones, set here instead so they also cover `_next/static` and the other assets the
   * middleware matcher deliberately skips.
   */
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          // A .js served as text/plain must not be executed because a sniffer liked it.
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          // `frame-ancestors 'none'` in the CSP is the modern form; this is the fallback
          // for anything that does not implement it.
          { key: 'X-Frame-Options', value: 'DENY' },
          // The full URL of a bid workspace names a tender; only the origin may leak.
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
          // Nothing here uses a camera, a microphone or a location, so nothing may.
          {
            key: 'Permissions-Policy',
            value: 'camera=(), microphone=(), geolocation=(), interest-cohort=()',
          },
          // Inert over plain http, which is what local development is; it costs nothing
          // to carry and is the one header that must already be right on the first
          // https response a deployment ever serves.
          {
            key: 'Strict-Transport-Security',
            value: 'max-age=31536000; includeSubDomains',
          },
        ],
      },
    ]
  },
}

export default nextConfig
