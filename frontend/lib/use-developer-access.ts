'use client'

/**
 * Whether this account may open the developer console (story S4.6.2).
 *
 * **The server is the gate; the browser only asks.** Nothing in the session says whether an
 * email is on the API's `DEVELOPER_EMAILS`, and adding a field for it would be a second
 * copy of an authorisation the API already makes on every `/dev/*` request. So the answer
 * is the API's own: `GET /dev/settings` answers 200 for a developer, **403** for a signed-in
 * account that is not one, and **404** on a production API where the routes do not exist.
 * A 401 is read the same way — no session yet is not a developer yet.
 *
 * Definitive answers are cached for the tab, so navigating between pages asks once, not on
 * every sidebar mount. Anything else — a transport failure, a 5xx — is *not* cached and
 * leaves the state `unknown`: the console stays hidden for now and the next mount asks
 * again, rather than a flaky API denying a developer their panel until a hard reload.
 *
 * `unknown` hides rather than shows. An entry that appears a moment after the shell renders
 * is a small thing; one that a non-developer sees vanish is a promise withdrawn.
 *
 * **`shouldAsk` holds the question until there is a session to ask with.** Since the shell
 * paints before the session settles (2026-09-15 audit, M7), the sidebar's first render
 * happens while `SessionProvider` is still reading `localStorage` and before it has set the
 * bearer token. A probe sent then is a 401 — and a 401 is cached as `denied` for the rest of
 * the tab, which is right for a signed-in non-developer and wrong here: it would hide the
 * console from a developer until a hard reload. The caller says when the session is known
 * (`NavGroups` passes its status); until then the hook asks nothing and reports `unknown`.
 */
import { useEffect, useState } from 'react'

import { ApiError } from './api-client'
import { loadDevSettings } from './dev'

export type DeveloperAccess = 'unknown' | 'granted' | 'denied'

const DENYING_STATUSES: ReadonlySet<number> = new Set([401, 403, 404])

let settled: DeveloperAccess | undefined
let inFlight: Promise<DeveloperAccess> | undefined

/** Asks the API once; concurrent callers share the request and definitive answers stick. */
export function probeDeveloperAccess(): Promise<DeveloperAccess> {
  if (settled !== undefined) {
    return Promise.resolve(settled)
  }
  inFlight ??= loadDevSettings()
    .then((): DeveloperAccess => 'granted')
    .catch((error: unknown): DeveloperAccess =>
      error instanceof ApiError && DENYING_STATUSES.has(error.status) ? 'denied' : 'unknown'
    )
    .then((access) => {
      if (access !== 'unknown') {
        settled = access
      }
      inFlight = undefined
      return access
    })
  return inFlight
}

/**
 * @param shouldAsk `false` defers the probe — see the docblock above. Defaults to asking at
 * once, which is right for a caller that only mounts once a session exists.
 */
export function useDeveloperAccess(shouldAsk = true): DeveloperAccess {
  const [access, setAccess] = useState<DeveloperAccess>(settled ?? 'unknown')

  useEffect(() => {
    if (!shouldAsk) return
    let isCurrent = true
    void probeDeveloperAccess().then((answer) => {
      if (isCurrent) {
        setAccess(answer)
      }
    })
    return () => {
      isCurrent = false
    }
  }, [shouldAsk])

  return access
}
