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

export function useDeveloperAccess(): DeveloperAccess {
  const [access, setAccess] = useState<DeveloperAccess>(settled ?? 'unknown')

  useEffect(() => {
    let isCurrent = true
    void probeDeveloperAccess().then((answer) => {
      if (isCurrent) {
        setAccess(answer)
      }
    })
    return () => {
      isCurrent = false
    }
  }, [])

  return access
}
