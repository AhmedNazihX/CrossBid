/**
 * The browser's Supabase Auth client (story S4.1.1).
 *
 * **Auth only.** The plan's boundary rule is that all data goes through FastAPI; the one
 * thing the browser talks to Supabase for is sign-in, so that no password or magic-link
 * code lives in this repo. Nothing here reads or writes a table.
 *
 * **Two modes, and they are mutually exclusive.** The app signs users in when
 * `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY` are set at build time
 * *and* `NEXT_PUBLIC_DEV_COMPANY_ID` is not — otherwise it stays on the S0.3.1 dev bridge,
 * `X-Dev-Company` and no session at all, which is what the demo and every screen built
 * before this story run on.
 *
 * **The dev bridge winning is the load-bearing half of that rule.** `infra/docker-compose.yml`
 * has passed `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY` as build args
 * since S0.1, derived from the same `.env` the API reads — so a stack whose API runs
 * `AUTH_MODE=dev` would otherwise boot a browser in session mode against it, and every
 * screen would 401: the browser sends a token the API ignores, and withholds the header it
 * actually wants. The backend has one switch for this (`AUTH_MODE`) and so does the
 * browser; clearing `NEXT_PUBLIC_DEV_COMPANY_ID` is how you throw it.
 *
 * **The anon key is not a secret.** It is inlined into the client bundle by design and
 * carries no privileges beyond what Supabase's own policies allow an anonymous visitor.
 * The service-role key never leaves the server and is not read here.
 */
import type { SupabaseClient } from '@supabase/supabase-js'

import { DEV_COMPANY_ID } from './api-client'

function readOptionalEnv(value: string | undefined): string | undefined {
  const trimmed = value?.trim() ?? ''
  return trimmed.length === 0 ? undefined : trimmed
}

/** The hosted project's API URL, or `undefined` when the app runs on the dev bridge. */
export const SUPABASE_URL = readOptionalEnv(process.env.NEXT_PUBLIC_SUPABASE_URL)

/** The public anon key. Inlined at build time; see the note above on why that is safe. */
export const SUPABASE_ANON_KEY = readOptionalEnv(process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY)

/**
 * Whether this build signs people in.
 *
 * Both Supabase values or neither — a half-configured build would render a login form that
 * cannot send anything, which is worse than not offering one — and never while the dev
 * bridge is configured, for the reason above.
 */
export const isAuthEnabled =
  SUPABASE_URL !== undefined && SUPABASE_ANON_KEY !== undefined && DEV_COMPANY_ID === undefined

let client: Promise<SupabaseClient> | undefined

/**
 * The one client for this tab, or `null` on the dev bridge.
 *
 * Built lazily and never during a server render: the session lives in `localStorage`, and
 * a client constructed where there is no `window` would start out signed out and then
 * disagree with the browser that hydrates it.
 *
 * **The import is dynamic, and that is the point of the `Promise`.** `SessionProvider` sits
 * in the root layout so that one session serves every route, and a static import would
 * therefore put ~80 kB of auth client into the first load of every page — the marketing
 * page included, which needs it only if a visitor clicks Sign in. This way the chunk is
 * fetched when a session is actually looked for, and never at all on the dev bridge.
 */
export function getSupabaseClient(): Promise<SupabaseClient | null> {
  if (!isAuthEnabled || typeof window === 'undefined') return Promise.resolve(null)
  client ??= import('@supabase/supabase-js').then(({ createClient }) =>
    createClient(SUPABASE_URL as string, SUPABASE_ANON_KEY as string, {
      auth: {
        // The magic link lands on /auth/callback carrying a code; `detectSessionInUrl` is
        // what exchanges it for a session there, and PKCE is what stops that code being
        // replayable by anyone who sees the URL in a referrer or a mail scanner's logs.
        flowType: 'pkce',
        detectSessionInUrl: true,
        persistSession: true,
        autoRefreshToken: true,
      },
    })
  )
  return client
}

/**
 * Where Supabase sends the browser after the link is followed.
 *
 * `next` rides along so that a deep link survives the round trip through the mailbox:
 * asking for `/bids/42` while signed out lands back on `/bids/42`, not on the dashboard.
 * It is re-validated on arrival (`safeNextPath`) rather than trusted because it was ours
 * when it left.
 */
export function authCallbackUrl(next?: string): string {
  const base = `${window.location.origin}/auth/callback`
  return next === undefined ? base : `${base}?next=${encodeURIComponent(next)}`
}
