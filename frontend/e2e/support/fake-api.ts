/**
 * The API, replaced at the browser's network edge (story S7.7).
 *
 * Every journey in `e2e/` drives the real Next app — its HTML, its CSS tokens, its hydration,
 * its tab strip — against answers the test wrote, typed from the same generated schema the
 * app compiles against (`lib/api.ts`). The API process itself is not started, for three
 * reasons the 2026-09-15 audit's blockers make concrete:
 *
 * - Each blocker was a *frontend* defect: two siblings each fetching once, a default the next
 *   step filtered out, a colour token that did not exist, a flex child that shrank to 2 px.
 *   None depended on *what* the API answered — only on when, and in what shape — and a test
 *   that dictates both reproduces the defect on every run.
 * - The states those journeys need are expensive or unreachable through the real API on a
 *   laptop: a document reaching `ready` needs Supabase Storage and an embeddings call; a bid
 *   with a verdict is a five-minute, ~$1.38 graph run (CLAUDE.md).
 * - The stack a developer has running points at the owner's hosted project. A suite that
 *   uploaded files and started bids there would create real rows in real tables every run.
 *
 * **It stands in for Storage too.** The source panel frames the signed URL the API hands
 * out, and the CSP frames only `'self'` and the Supabase origin — so the e2e server is built
 * with `NEXT_PUBLIC_SUPABASE_URL` set to this fake's origin, and a test that shows a document
 * stubs both `GET /documents/{id}/url` and the page that URL names (see `sourcePageStubs`).
 *
 * **Nothing leaves the page.** One catch-all route lets the app's own origin through,
 * dispatches the API origin to the handlers a test registered, and fulfils anything else
 * with a 500 whose `detail` names the call — recorded in `unexpected`, which the `api`
 * fixture asserts is empty. A screen that starts calling a route nobody stubbed fails its
 * test by name, rather than reaching whatever happens to listen on port 8000.
 *
 * **An answer may also be no answer.** What the browser sees when the API is down — or when
 * a response is refused by CORS, as it was on 2026-09-16 while migrations were pending and
 * Starlette dropped the headers from its 500 — is neither a status nor a body but a rejected
 * `fetch`; `{ failure: 'abort' }` reproduces exactly that. `{ failure: 'hang' }` is a request
 * that never settles: nothing fulfils it, and the page's own deadline is what a test then
 * waits for. A fulfilled 500 is *not* the CORS case, because Playwright adds
 * `Access-Control-Allow-Origin` to every fulfilled cross-origin response itself.
 *
 * Handlers are matched newest-first, so a test can override what its `beforeEach` set up.
 */
import type { Page, Route } from '@playwright/test'

export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'

export interface FakeResponse {
  readonly status: number
  /** A JSON body — what every API route answers with. */
  readonly json?: unknown
  /** A raw body instead, e.g. the page a signed document URL opens; `contentType` names it. */
  readonly body?: string
  readonly contentType?: string
}

/** No answer at all: the request fails at the transport (`abort`), or never settles (`hang`). */
export interface FakeFailure {
  readonly failure: 'abort' | 'hang'
}

export type FakeAnswer = FakeResponse | FakeFailure

export interface RecordedRequest {
  readonly method: string
  /** Path and query without the origin, e.g. `/documents/1234`. */
  readonly path: string
  /** The body as text — JSON or multipart — or `undefined` when the request carried none. */
  readonly body: string | undefined
}

export type Responder = (request: RecordedRequest, match: RegExpMatchArray) => FakeAnswer

interface Handler {
  readonly method: HttpMethod
  readonly path: RegExp
  readonly respond: Responder
}

/** What an un-stubbed call gets: a FastAPI-shaped refusal the screen can show verbatim. */
const UNSTUBBED_STATUS = 500

/**
 * The app fetches cross-origin with `credentials: 'omit'` (api-client.ts), so a wildcard
 * origin is both sufficient and exactly what a browser will accept for that mode.
 */
const CORS_HEADERS: Readonly<Record<string, string>> = {
  'access-control-allow-origin': '*',
  'access-control-allow-methods': 'GET,POST,PUT,PATCH,DELETE,OPTIONS',
  'access-control-allow-headers': '*',
}

function escapeForRegExp(literal: string): string {
  return literal.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function toPathPattern(path: string | RegExp): RegExp {
  return typeof path === 'string' ? new RegExp(`^${escapeForRegExp(path)}$`) : path
}

function toResponder(answer: Responder | FakeAnswer): Responder {
  return typeof answer === 'function' ? answer : () => answer
}

/**
 * Answers in turn, then repeats the last one for ever — the shape of anything the app polls:
 * a document that is `parsed` on one poll and `ready` on the next stays `ready`.
 */
export function sequence(answers: readonly FakeAnswer[]): Responder {
  const last = answers[answers.length - 1]
  if (last === undefined) {
    throw new Error('sequence() needs at least one answer')
  }
  let served = 0
  return () => {
    const answer = answers[served] ?? last
    served += 1
    return answer
  }
}

/** The value of one plain field in a multipart body, or `undefined` when it is not there. */
export function multipartField(body: string | undefined, name: string): string | undefined {
  const match = body?.match(
    new RegExp(`name="${escapeForRegExp(name)}"\\r\\n\\r\\n([^\\r\\n]*)`)
  )
  return match?.[1]
}

/** The filename of the first file part in a multipart body, or `undefined`. */
export function multipartFilename(body: string | undefined): string | undefined {
  return body?.match(/filename="([^"]*)"/)?.[1]
}

export class FakeApi {
  private handlers: readonly Handler[] = []
  private recorded: readonly RecordedRequest[] = []
  private unstubbed: readonly string[] = []

  constructor(
    private readonly apiOrigin: string,
    private readonly appOrigin: string
  ) {}

  /** Registers an answer for `method` + `path` (exact string, or a RegExp on the pathname). */
  on(method: HttpMethod, path: string | RegExp, answer: Responder | FakeAnswer): void {
    const handler: Handler = { method, path: toPathPattern(path), respond: toResponder(answer) }
    this.handlers = [handler, ...this.handlers]
  }

  /** Every call that reached the API origin, in order, stubbed or not. */
  get requests(): readonly RecordedRequest[] {
    return this.recorded
  }

  /** `METHOD /path` for every call nothing answered, and every call to a third origin. */
  get unexpected(): readonly string[] {
    return this.unstubbed
  }

  async handle(route: Route): Promise<void> {
    const request = route.request()
    const url = new URL(request.url())
    if (url.origin === this.appOrigin) {
      await route.fallback()
      return
    }
    if (request.method() === 'OPTIONS') {
      await route.fulfill({ status: 204, headers: CORS_HEADERS })
      return
    }
    const recorded: RecordedRequest = {
      method: request.method(),
      path: `${url.pathname}${url.search}`,
      body: request.postDataBuffer()?.toString('utf8'),
    }
    if (url.origin !== this.apiOrigin) {
      this.unstubbed = [
        ...this.unstubbed,
        `${recorded.method} ${url.href} (not the API origin)`,
      ]
      await this.refuse(route, recorded)
      return
    }
    this.recorded = [...this.recorded, recorded]
    const found = this.find(recorded.method, url.pathname)
    if (found === undefined) {
      this.unstubbed = [...this.unstubbed, `${recorded.method} ${recorded.path}`]
      await this.refuse(route, recorded)
      return
    }
    const answer = found.handler.respond(recorded, found.match)
    if ('failure' in answer) {
      if (answer.failure === 'abort') await route.abort('failed')
      return
    }
    await route.fulfill(
      answer.body === undefined
        ? { status: answer.status, json: answer.json, headers: CORS_HEADERS }
        : {
            status: answer.status,
            body: answer.body,
            contentType: answer.contentType,
            headers: CORS_HEADERS,
          }
    )
  }

  private find(
    method: string,
    pathname: string
  ): { readonly handler: Handler; readonly match: RegExpMatchArray } | undefined {
    for (const handler of this.handlers) {
      if (handler.method !== method) continue
      const match = pathname.match(handler.path)
      if (match !== null) return { handler, match }
    }
    return undefined
  }

  private refuse(route: Route, request: RecordedRequest): Promise<void> {
    return route.fulfill({
      status: UNSTUBBED_STATUS,
      json: { detail: `e2e: no stub answers ${request.method} ${request.path}` },
      headers: CORS_HEADERS,
    })
  }
}

export interface FakeApiOrigins {
  /** Where the app under test believes the API is: its build-time `NEXT_PUBLIC_API_URL`. */
  readonly apiOrigin: string
  /** The app itself; its requests pass through untouched. */
  readonly appOrigin: string
}

export async function installFakeApi(page: Page, origins: FakeApiOrigins): Promise<FakeApi> {
  const api = new FakeApi(origins.apiOrigin, origins.appOrigin)
  await page.route('**/*', (route) => api.handle(route))
  return api
}
