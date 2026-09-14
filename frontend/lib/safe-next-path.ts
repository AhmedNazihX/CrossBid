/**
 * The `?next=` round trip, kept from becoming an open redirect (story S4.1.1).
 *
 * `RequireSession` puts the path a signed-out visitor asked for into `?next=`, it travels
 * to Supabase as part of `emailRedirectTo` and comes back on the callback URL. Anything
 * that survives a round trip through an email is attacker-supplied by the time we read it:
 * a crafted link would otherwise send someone who has just proved their identity straight
 * to a page of somebody else's choosing, which is exactly the shape of a credible phish.
 *
 * So only a same-site absolute path is accepted. `//evil.example` is rejected because a
 * protocol-relative URL is a different origin wearing a path's clothes, and `/\evil` for
 * the same reason once a browser normalises the backslash.
 */
export const DEFAULT_AFTER_SIGN_IN = '/dashboard'

export function safeNextPath(value: string | null | undefined): string {
  if (value === null || value === undefined) return DEFAULT_AFTER_SIGN_IN
  const trimmed = value.trim()
  const isSameSitePath =
    trimmed.startsWith('/') && !trimmed.startsWith('//') && !trimmed.startsWith('/\\')
  return isSameSitePath ? trimmed : DEFAULT_AFTER_SIGN_IN
}
