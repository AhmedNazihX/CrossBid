/**
 * The Content-Security-Policy, and the per-request nonce it needs (ADR-0036).
 *
 * This is the control that actually addresses the threat ADR-0035 left open: the session
 * lives in `localStorage`, so any script that runs on this origin can read it, and the
 * defence is to make sure no script runs that we did not put there. Every other mitigation
 * in that ADR limits what a successful injection can *do*; this one is about the injection.
 *
 * **Every route, including the marketing page.** `localStorage` is scoped to the origin,
 * not to the page, so an injection on `/` reads the token that `/dashboard` stored. Exempting
 * the one public page would have exempted the one an attacker can reach without signing in.
 * The cost is that `/` is rendered per request rather than prerendered — it is served by a
 * Node process in a container, not a CDN, so that is compute rather than correctness.
 *
 * **Nonce, not `'unsafe-inline'`.** Next emits its own inline hydration scripts, so a policy
 * that does not name them has to allow *all* inline script — which is the thing being
 * defended against, spelled as a header. A fresh nonce per request is the supported way, and
 * setting the policy on the *request* headers as well as the response is what lets Next find
 * it and stamp its own scripts with it.
 *
 * **`'strict-dynamic'` is what makes it hold.** Without it the policy is a list of origins,
 * and any of them serving one unsafe file re-opens the door. With it, only the nonced script
 * is trusted, plus whatever that script loads itself — which is exactly Next's chunk loader
 * and nothing else.
 *
 * `style-src` keeps `'unsafe-inline'`: React writes two `style` props in `brand-reveal.tsx`
 * as element attributes, and there is no nonce mechanism for those. Inline *style* is a far
 * smaller hazard than inline script — it cannot execute — and the alternative is rewriting
 * working, measured animation code to buy very little.
 */
import { NextResponse, type NextRequest } from 'next/server'

/** The API, and Supabase Auth plus Storage: the only two origins the browser may reach. */
const API_ORIGIN = originOf(process.env.NEXT_PUBLIC_API_URL, 'http://localhost:8000')
const SUPABASE_ORIGIN = originOf(process.env.NEXT_PUBLIC_SUPABASE_URL, undefined)

const IS_DEVELOPMENT = process.env.NODE_ENV === 'development'

export function middleware(request: NextRequest) {
  const nonce = btoa(crypto.randomUUID())
  const policy = contentSecurityPolicy(nonce, isSecure(request))

  // Next reads the nonce back out of this header to stamp its own inline scripts, so the
  // policy has to travel with the request, not only with the response.
  const headers = new Headers(request.headers)
  headers.set('x-nonce', nonce)
  headers.set('content-security-policy', policy)

  const response = NextResponse.next({ request: { headers } })
  response.headers.set('content-security-policy', policy)
  return response
}

/**
 * Whether this response is being served over https, directly or behind a proxy.
 *
 * `x-forwarded-proto` is what a terminating load balancer sets, and `nextUrl.protocol` is
 * http in that case even though the browser's connection is not — so both are consulted.
 */
function isSecure(request: NextRequest): boolean {
  const forwarded = request.headers.get('x-forwarded-proto')?.split(',')[0]?.trim()
  return forwarded === 'https' || request.nextUrl.protocol === 'https:'
}

function contentSecurityPolicy(nonce: string, secure: boolean): string {
  const connect = ["'self'", API_ORIGIN, SUPABASE_ORIGIN, IS_DEVELOPMENT ? 'ws:' : undefined]
  const frame = ["'self'", SUPABASE_ORIGIN]
  return [
    "default-src 'self'",
    // `unsafe-eval` is the dev server's hot reload and is never emitted in a real build.
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${IS_DEVELOPMENT ? " 'unsafe-eval'" : ''}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data:",
    "media-src 'self'",
    "font-src 'self'",
    `connect-src ${join(connect)}`,
    // The source viewer iframes a signed Storage URL; nothing else may be framed.
    `frame-src ${join(frame)}`,
    "worker-src 'self' blob:",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    /*
     * Only where there is something to upgrade. On a plain-http origin this directive has
     * nothing to protect — everything is already local — and it actively breaks: it tells
     * the browser to rewrite every http subresource to https, and `http://localhost:3000`
     * has no https counterpart, so the chunks 404 and the page renders without its
     * JavaScript. Chrome exempts localhost from the upgrade and Safari has not, which is
     * how this arrives as "works in one browser, not the other" rather than as an error.
     */
    secure ? 'upgrade-insecure-requests' : undefined,
  ]
    .filter((directive): directive is string => directive !== undefined)
    .join('; ')
}

function join(sources: readonly (string | undefined)[]): string {
  return sources.filter((source): source is string => source !== undefined).join(' ')
}

function originOf(url: string | undefined, fallback: string | undefined): string | undefined {
  const trimmed = url?.trim() ?? ''
  if (trimmed.length === 0) return fallback
  try {
    return new URL(trimmed).origin
  } catch {
    // A malformed URL must not silently widen the policy; the app fails loudly elsewhere.
    return fallback
  }
}

export const config = {
  matcher: [
    /*
     * Documents only. Static assets carry no script and cannot be a CSP context; the
     * constant headers in `next.config.ts` still apply to them.
     */
    '/((?!_next/static|_next/image|favicon.ico).*)',
  ],
}
