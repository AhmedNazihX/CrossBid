'use client'

/**
 * Who is signed in, at the foot of the sidebar (story S4.1.1).
 *
 * This is the block `ui_kits/app/Shell.jsx` draws there and `AdvisoryNote` has been
 * standing in for: a 32 px stone-200 circle of initials, a 14 px medium line, a 12 px muted
 * line under it. The kit shows a person and their company; here the second line is the way
 * out, because a shared machine with no visible sign-out is how one bidder ends up reading
 * another's matrix.
 *
 * Renders nothing on the dev bridge, where there is no person to name.
 */
import { useSession } from '@/components/auth/session-provider'

export function AccountBlock() {
  const { status, email, signOut } = useSession()

  if (status !== 'signedIn' || email === undefined) return null

  return (
    <div className="flex items-center gap-2.5 p-2.5">
      <span
        aria-hidden
        className="inline-flex size-8 shrink-0 items-center justify-center rounded-full bg-stone-200 text-[12px] font-semibold leading-none text-text-secondary"
      >
        {initials(email)}
      </span>
      <div className="min-w-0">
        <p className="m-0 truncate text-[14px] font-medium leading-[1.2] text-text-primary">
          {email}
        </p>
        <button
          type="button"
          onClick={() => void signOut()}
          className="rounded-sm text-[12px] leading-[1.2] text-text-muted underline-offset-2 hover:text-text-primary hover:underline"
        >
          Sign out
        </button>
      </div>
    </div>
  )
}

/** Up to two letters from the address, so the circle reads as a person rather than a dot. */
function initials(email: string): string {
  const local = email.split('@')[0] ?? email
  const parts = local.split(/[._-]+/).filter((part) => part.length > 0)
  const letters =
    parts.length > 1 ? `${parts[0]?.[0] ?? ''}${parts[1]?.[0] ?? ''}` : local.slice(0, 2)
  return letters.toUpperCase()
}
