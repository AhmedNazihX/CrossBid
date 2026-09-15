/**
 * Typed calls for the `/dev/*` routes — the developer console (story S4.6.2, over S1.4.1's
 * settings read and S5.2's cost report).
 *
 * Every type here comes from `components['schemas']` — `lib/api.ts` is generated from the live
 * OpenAPI schema and never hand-edited (S0.4.2). The `PUT /dev/settings` route and the two
 * fields S4.6.2 added to the settings response were briefly declared locally, behind one
 * documented cast, until the schema was regenerated; that scaffolding is gone, and a field
 * the backend renames now stops compiling here rather than failing at run time.
 *
 * **The row is sent whole.** `AppSettingsRow` mirrors the backend's: five nullable columns,
 * and a `null` means "back to the `settings.default.yaml` value". A save therefore carries
 * every field, and `components/dev/settings-draft.ts` nulls the ones equal to their default
 * — there is no partial update, because a merge that skipped absent fields could never
 * clear an override (`crossbid/readmodel/app_settings.py`).
 */
import type { components } from './api'
import { apiRequest } from './api-client'

export type ModelRole = components['schemas']['ModelRole']
export type ModelSlugs = components['schemas']['ModelSlugs']
export type ToolDescriptor = components['schemas']['ToolDescriptor']
export type AgentSettings = components['schemas']['AgentSettings']
export type UsageTotals = components['schemas']['UsageTotals']
export type NodeUsage = components['schemas']['NodeUsage']
export type BidUsage = components['schemas']['BidUsage']
export type DevCosts = components['schemas']['DevCostsResponse']

/** The `settings.default.yaml` value behind each editable field, so the panel can mark a
 * field as overridden and reset it. */
export type EditableDefaults = components['schemas']['EditableDefaults']

export type DevSettings = components['schemas']['DevSettingsResponse']

/** The `app_settings` row — the request body of `PUT /dev/settings`. `models` may name any
 * subset of the switchable roles; `embed` is refused by the route. */
export type AppSettingsRow = components['schemas']['AppSettingsRow']

const DEV_SETTINGS_PATH = '/dev/settings'
const DEV_COSTS_PATH = '/dev/costs'

/** How many bids the cost report lists; the API caps the parameter at 200. */
export const COST_BID_LIMIT = 50

/**
 * What the agent is configured to do. Answers **403** for an account not on the API's
 * developer list and **404** on a production API — both mean "not for this caller", and
 * `lib/use-developer-access.ts` reads them that way to hide the console.
 */
export function loadDevSettings(signal?: AbortSignal): Promise<DevSettings> {
  return apiRequest('get', DEV_SETTINGS_PATH, { signal })
}

/**
 * Replaces the `app_settings` row and resolves with the settings now in force — for the
 * next request *and* the next bid run; a run already in flight finishes on the settings it
 * started with. **422** names the field that was refused (`lib/field-errors.ts` places it),
 * and nothing is stored in that case.
 */
export function saveDevSettings(
  row: AppSettingsRow,
  signal?: AbortSignal
): Promise<DevSettings> {
  return apiRequest('put', DEV_SETTINGS_PATH, { body: row, signal })
}

/**
 * What this company's runs have spent, per node and per bid. Tenant-scoped, unlike the
 * settings: a developer sees the numbers of the company they are signed in as.
 */
export function loadDevCosts(signal?: AbortSignal): Promise<DevCosts> {
  return apiRequest('get', DEV_COSTS_PATH, { query: { limit: COST_BID_LIMIT }, signal })
}
