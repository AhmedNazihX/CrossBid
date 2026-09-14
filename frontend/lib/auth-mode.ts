/**
 * Which way this build authenticates, in one place (stories S0.3.1, S4.1.1).
 *
 * **One variable, named after the one the API reads.** `NEXT_PUBLIC_AUTH_MODE` mirrors the
 * backend's `AUTH_MODE` and takes the same two values, because the two halves have to
 * agree and the fastest way to keep them agreeing is to make them look the same in the
 * `.env`. A browser in session mode against an API in dev mode sends a token nothing
 * verifies and withholds the header it wants; the reverse sends a header nothing believes.
 * Either way every screen 401s, and nothing on the screen says why.
 *
 * The first cut of this inferred the mode from whether `NEXT_PUBLIC_DEV_COMPANY_ID`
 * happened to be set. That was wrong in the way implicit switches usually are: turning
 * sign-in on meant *deleting* a line in a file the API does not read, in a directory Next
 * insists on, and getting it wrong looked exactly like getting it right — the app came up,
 * the guard stayed off, and no login page was ever reached. `configurationProblem` below
 * is the other half of the fix: a mode that cannot work says so on the login screen rather
 * than silently falling back.
 *
 * Everything here is `NEXT_PUBLIC_*`, so it is inlined into the client bundle at build
 * time and must never hold a secret. The Supabase anon key is not one: it carries no
 * privilege of its own and is meant to be public.
 */

export type AuthMode = 'dev' | 'supabase'

function readOptionalEnv(value: string | undefined): string | undefined {
  const trimmed = value?.trim() ?? ''
  return trimmed.length === 0 ? undefined : trimmed
}

/**
 * `dev` unless the build says otherwise.
 *
 * Defaulting to the bridge keeps every screen built before S4.1.1 working in a checkout
 * that has never heard of this variable, and an unreadable value is the bridge too — a
 * typo must not be the thing that decides a deployment is authenticated.
 */
export const AUTH_MODE: AuthMode =
  readOptionalEnv(process.env.NEXT_PUBLIC_AUTH_MODE)?.toLowerCase() === 'supabase'
    ? 'supabase'
    : 'dev'

/** The hosted project's API URL. Required by `supabase` mode, unused by `dev`. */
export const SUPABASE_URL = readOptionalEnv(process.env.NEXT_PUBLIC_SUPABASE_URL)

/** The public anon key. Required by `supabase` mode, unused by `dev`. */
export const SUPABASE_ANON_KEY = readOptionalEnv(process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY)

/** Company id sent as `X-Dev-Company`. Required by `dev` mode, never sent by `supabase`. */
export const DEV_COMPANY_ID = readOptionalEnv(process.env.NEXT_PUBLIC_DEV_COMPANY_ID)

/** Whether this build signs people in: the mode asks for it and it can be done. */
export const isAuthEnabled =
  AUTH_MODE === 'supabase' && SUPABASE_URL !== undefined && SUPABASE_ANON_KEY !== undefined

/**
 * What is missing, as a sentence for a screen, or `undefined` when the build is coherent.
 *
 * A half-configured build is the failure worth naming: it comes up, looks normal, and is
 * wrong in a way that only shows as 401s on screens the person had no reason to connect
 * with an environment variable.
 */
export const configurationProblem: string | undefined = describeProblem()

function describeProblem(): string | undefined {
  if (AUTH_MODE === 'supabase') {
    const missing = [
      SUPABASE_URL === undefined ? 'NEXT_PUBLIC_SUPABASE_URL' : undefined,
      SUPABASE_ANON_KEY === undefined ? 'NEXT_PUBLIC_SUPABASE_ANON_KEY' : undefined,
    ].filter((name): name is string => name !== undefined)
    return missing.length === 0
      ? undefined
      : `NEXT_PUBLIC_AUTH_MODE=supabase, but ${missing.join(' and ')} ${
          missing.length === 1 ? 'is' : 'are'
        } not set. Set them in frontend/.env.local and restart the dev server.`
  }
  return DEV_COMPANY_ID === undefined
    ? 'NEXT_PUBLIC_AUTH_MODE=dev, but NEXT_PUBLIC_DEV_COMPANY_ID is not set, so every ' +
        'request is unauthenticated. Run `make seed-dev`, which prints the line to paste ' +
        'into frontend/.env.local, and restart the dev server.'
    : undefined
}
