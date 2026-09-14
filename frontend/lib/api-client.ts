/**
 * Typed `fetch` wrapper for the Crossbid API.
 *
 * `./api.ts` is generated from the backend's live OpenAPI schema (`npm run gen:api`,
 * story S0.4.2) and is the only thing the two apps share. Everything here is derived
 * from its `paths` type, so a route or field that the backend does not expose does not
 * compile here either.
 *
 * Boundary rules this file encodes (docs/project-plan.md -> "Frontend <-> backend
 * boundary"): the browser calls FastAPI directly on its own origin, every call carries
 * `Authorization: Bearer <jwt>`, cookies are never sent, and a non-2xx answer becomes an
 * `ApiError` rather than a silently-undefined payload.
 *
 * The token comes from `SessionProvider` (S4.1.1), which calls `setAccessToken` on every
 * Supabase auth change. It is held in a module variable rather than threaded through every
 * call site for the same reason `DEV_COMPANY_ID` is: a bearer token is a property of the
 * tab, not of one request, and a refresh that replaced it would otherwise have to be
 * pushed through every hook and screen to take effect. A caller may still pass `token`
 * explicitly, which wins.
 *
 * The S0.3.1 dev bridge still stands in under `NEXT_PUBLIC_AUTH_MODE=dev`: every call then
 * carries `X-Dev-Company: <uuid>`, which the API believes only under its own
 * `AUTH_MODE=dev`. That header is attached here and nowhere else, and **only in dev mode** —
 * sending it alongside a real session would be a second, self-asserted claim about who is
 * calling, sitting next to a verified one.
 *
 * Deliberately not here — React hooks and caching belong to E4 (the 2 s poll lives in
 * `./use-polling.ts`, S4.2.2).
 */
import type { paths } from './api'
import { AUTH_MODE, DEV_COMPANY_ID } from './auth-mode'

/** Used when `NEXT_PUBLIC_API_URL` is absent, i.e. local development. */
const DEFAULT_API_BASE_URL = 'http://localhost:8000'

/** `ApiError.status` when the request never reached the API (DNS, CORS, offline, abort). */
export const TRANSPORT_ERROR_STATUS = 0

/** The S0.3.1 dev-bridge header; must match `crossbid.auth.DEV_COMPANY_HEADER`. */
export const DEV_COMPANY_HEADER = 'X-Dev-Company'

/**
 * Base URL of the API, without a trailing slash.
 *
 * `NEXT_PUBLIC_*` is inlined at build time, so this is fixed per image — and must never
 * hold a secret, because the browser sees it.
 */
export const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL ?? DEFAULT_API_BASE_URL).replace(
  /\/+$/,
  ''
)

let accessToken: string | undefined

/**
 * Set the bearer token every later request carries, or clear it with `undefined`.
 *
 * Called only by `SessionProvider`. Exported rather than assigned so that the one writer
 * is greppable: a second caller would be a second source of truth for who is signed in.
 */
export function setAccessToken(token: string | undefined): void {
  accessToken = token
}

/** HTTP methods the client supports. `options`, `head` and `trace` are not used. */
export type HttpMethod = 'get' | 'post' | 'put' | 'patch' | 'delete'

/** Path templates in the schema that define `M`, e.g. `PathFor<'post'>` is `'/documents' | '/bids'`. */
export type PathFor<M extends HttpMethod> = {
  [P in keyof paths]: paths[P] extends { [K in M]: object } ? P : never
}[keyof paths]

/**
 * The generated operation object behind one path + method pair, or `never` when the
 * schema does not define that method on that path.
 */
export type ApiOperation<P extends keyof paths, M extends HttpMethod> = M extends keyof paths[P]
  ? NonNullable<paths[P][M]>
  : never

type JsonOf<T> = T extends { content: { 'application/json': infer J } } ? J : never

type ParametersOf<O> = O extends { parameters: infer Params } ? Params : never

type SuccessStatus = 200 | 201 | 202 | 204

/** JSON body of the operation's success response — the resolved value of a call. */
export type ResponseBody<P extends keyof paths, M extends HttpMethod> =
  ApiOperation<P, M> extends { responses: infer Responses }
    ? Responses extends object
      ? JsonOf<Responses[Extract<keyof Responses, SuccessStatus>]>
      : never
    : never

/** Values for the `{placeholders}` in the path template; `never` when it has none. */
export type PathParams<P extends keyof paths, M extends HttpMethod> =
  ParametersOf<ApiOperation<P, M>> extends { path: infer Values } ? Values : never

/** Query string parameters the operation accepts; `never` when it accepts none. */
export type QueryParams<P extends keyof paths, M extends HttpMethod> =
  ParametersOf<ApiOperation<P, M>> extends { query: infer Values } ? Values : never

type DeclaredRequestBody<P extends keyof paths, M extends HttpMethod> = NonNullable<
  ApiOperation<P, M> extends { requestBody?: infer Body } ? Body : never
>

type MultipartOf<T> = T extends { content: { 'multipart/form-data': infer F } } ? F : never

/** JSON request body the operation accepts; `never` when it accepts none. */
export type RequestBody<P extends keyof paths, M extends HttpMethod> = JsonOf<
  DeclaredRequestBody<P, M>
>

/**
 * The multipart form the operation accepts (its field names and types); `never` when the
 * operation is not a file upload. Only `POST /documents` declares one today.
 */
export type MultipartBody<P extends keyof paths, M extends HttpMethod> = MultipartOf<
  DeclaredRequestBody<P, M>
>

export interface RequestOptions<P extends keyof paths, M extends HttpMethod> {
  /**
   * Supabase JWT. Normally omitted: the signed-in session's token is attached for you
   * (`setAccessToken`). Pass one to override it for a single call.
   */
  token?: string
  /** Path placeholder values. A placeholder left unfilled throws before any request. */
  path?: PathParams<P, M>
  /** Query parameters. `undefined` and `null` entries are dropped; arrays repeat the key. */
  query?: QueryParams<P, M>
  /** JSON request body. Sets `Content-Type` when present. */
  body?: RequestBody<P, M>
  /**
   * Multipart body for file uploads. Only accepted on operations that declare
   * `multipart/form-data`; `Content-Type` is left to the browser, which must add the
   * boundary itself. Mutually exclusive with `body`.
   */
  formData?: [MultipartBody<P, M>] extends [never] ? never : FormData
  signal?: AbortSignal
  /** Extra headers, merged last so a caller can override the defaults. */
  headers?: Readonly<Record<string, string>>
}

interface ApiErrorInit {
  readonly status: number
  readonly statusText: string
  readonly method: string
  readonly url: string
  readonly body: unknown
  readonly cause?: unknown
}

/**
 * A call that did not return a success status, or never reached the API at all
 * (`status === TRANSPORT_ERROR_STATUS`). `body` is the parsed JSON error payload when the
 * API sent one — FastAPI's `{ detail: ... }` — otherwise the raw text or `undefined`.
 */
export class ApiError extends Error {
  readonly status: number
  readonly statusText: string
  readonly method: string
  readonly url: string
  readonly body: unknown
  /** FastAPI's `detail`, written for the bidder to read; `undefined` when the API sent none. */
  readonly detail: string | undefined

  constructor(init: ApiErrorInit) {
    super(buildErrorMessage(init), init.cause === undefined ? undefined : { cause: init.cause })
    this.name = 'ApiError'
    this.status = init.status
    this.statusText = init.statusText
    this.method = init.method
    this.url = init.url
    this.body = init.body
    this.detail = extractDetail(init.body)
  }
}

/**
 * One sentence a bidder can act on, for any failure a call can throw.
 *
 * The API's `detail` is preferred verbatim — the backend writes it for the screen. A
 * transport failure has no `detail`, so it names the base URL: on a developer's machine
 * the usual cause is that the API is not running.
 */
export function describeApiError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.detail !== undefined) {
      return error.detail
    }
    if (error.status === TRANSPORT_ERROR_STATUS) {
      return `The API at ${API_BASE_URL} could not be reached. Check that it is running.`
    }
    return `The API answered ${error.status} ${error.statusText}.`
  }
  if (error instanceof Error && error.message.length > 0) {
    return error.message
  }
  return 'Something went wrong. Try again.'
}

/**
 * Calls one API operation.
 *
 * @throws ApiError on any non-2xx answer and on transport failure.
 * @throws TypeError when a path placeholder or query value is unusable — a caller bug.
 */
export async function apiRequest<M extends HttpMethod, P extends PathFor<M>>(
  method: M,
  pathTemplate: P,
  options: RequestOptions<P, M> = {}
): Promise<ResponseBody<P, M>> {
  const url = buildUrl(pathTemplate, options.path, options.query)
  const upperMethod = method.toUpperCase()
  const hasJsonBody = options.body !== undefined
  if (hasJsonBody && options.formData !== undefined) {
    throw new TypeError(`"${pathTemplate}" was given both a JSON body and a multipart body`)
  }

  const response = await sendRequest(url, {
    method: upperMethod,
    headers: buildHeaders(options, hasJsonBody),
    body: hasJsonBody ? JSON.stringify(options.body) : options.formData,
    signal: options.signal,
    // Bearer tokens only: no cookie is ever sent, so a locked-down CORS policy on the
    // API needs no credentialed-origin exception.
    credentials: 'omit',
  })

  const body = await readBody(response, upperMethod, url)

  if (!response.ok) {
    throw new ApiError({
      status: response.status,
      statusText: response.statusText,
      method: upperMethod,
      url,
      body,
    })
  }

  // The single trust boundary in this file. Runtime validation of every response would
  // need a schema library the project has not adopted; instead the generated types are
  // regenerated from the live schema and CI fails when they drift (S0.1.4).
  return body as ResponseBody<P, M>
}

async function sendRequest(url: string, init: RequestInit): Promise<Response> {
  try {
    return await fetch(url, init)
  } catch (cause) {
    throw new ApiError({
      status: TRANSPORT_ERROR_STATUS,
      statusText: 'Network request failed',
      method: typeof init.method === 'string' ? init.method : 'GET',
      url,
      body: undefined,
      cause,
    })
  }
}

/** Reads the response body as JSON, falling back to raw text, `undefined` when empty. */
async function readBody(response: Response, method: string, url: string): Promise<unknown> {
  let text: string
  try {
    text = await response.text()
  } catch (cause) {
    throw new ApiError({
      status: response.status,
      statusText: 'Response body could not be read',
      method,
      url,
      body: undefined,
      cause,
    })
  }

  if (text.length === 0) {
    return undefined
  }

  try {
    return JSON.parse(text) as unknown
  } catch {
    return text
  }
}

function buildHeaders(
  options: { token?: string; headers?: Readonly<Record<string, string>> },
  hasJsonBody: boolean
): Record<string, string> {
  return {
    Accept: 'application/json',
    ...(hasJsonBody ? { 'Content-Type': 'application/json' } : {}),
    ...bearer(options.token ?? accessToken),
    ...devCompany(),
    ...options.headers,
  }
}

function devCompany(): Record<string, string> {
  return AUTH_MODE === 'dev' && DEV_COMPANY_ID !== undefined
    ? { [DEV_COMPANY_HEADER]: DEV_COMPANY_ID }
    : {}
}

function bearer(token: string | undefined): Record<string, string> {
  return token === undefined ? {} : { Authorization: `Bearer ${token}` }
}

function buildUrl(pathTemplate: string, pathParams: unknown, query: unknown): string {
  const path = substitutePathParams(pathTemplate, pathParams)
  const search = buildSearchParams(query).toString()
  return search.length === 0 ? `${API_BASE_URL}${path}` : `${API_BASE_URL}${path}?${search}`
}

const PLACEHOLDER_PATTERN = /\{([^{}]+)\}/g

function substitutePathParams(pathTemplate: string, pathParams: unknown): string {
  const values = toEntryMap(pathParams)
  return pathTemplate.replace(PLACEHOLDER_PATTERN, (_match, name: string) => {
    const value = values.get(name)
    if (value === undefined || value === null) {
      throw new TypeError(`Missing path parameter "${name}" for "${pathTemplate}"`)
    }
    return encodeURIComponent(toScalar(value, name))
  })
}

function buildSearchParams(query: unknown): URLSearchParams {
  const search = new URLSearchParams()
  for (const [key, value] of toEntryMap(query)) {
    if (value === undefined || value === null) {
      continue
    }
    if (Array.isArray(value)) {
      for (const item of value as readonly unknown[]) {
        search.append(key, toScalar(item, key))
      }
      continue
    }
    search.append(key, toScalar(value, key))
  }
  return search
}

/** Normalises an optional generated parameter object into `Map<string, unknown>`. */
function toEntryMap(source: unknown): Map<string, unknown> {
  if (source === undefined || source === null || typeof source !== 'object') {
    return new Map()
  }
  return new Map<string, unknown>(Object.entries(source))
}

function toScalar(value: unknown, name: string): string {
  if (typeof value === 'string') {
    return value
  }
  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value)
  }
  throw new TypeError(`Parameter "${name}" must be a string, number or boolean`)
}

function buildErrorMessage(init: ApiErrorInit): string {
  const detail = extractDetail(init.body)
  const prefix =
    init.status === TRANSPORT_ERROR_STATUS
      ? `${init.method} ${init.url} failed: ${init.statusText}`
      : `${init.method} ${init.url} failed with ${init.status} ${init.statusText}`
  return detail === undefined ? prefix : `${prefix} — ${detail}`
}

/** Pulls a human-readable message out of FastAPI's `{ detail: ... }` error payload. */
function extractDetail(body: unknown): string | undefined {
  if (typeof body === 'string' && body.length > 0) {
    return body
  }
  if (body === null || typeof body !== 'object' || !('detail' in body)) {
    return undefined
  }
  const { detail } = body as { detail: unknown }
  if (typeof detail === 'string' && detail.length > 0) {
    return detail
  }
  return detail === undefined ? undefined : JSON.stringify(detail)
}
