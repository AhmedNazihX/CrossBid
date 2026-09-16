/**
 * FastAPI's 422 body, turned into a message per field (story S4.2.1).
 *
 * The story's criterion is "validation errors name the field", and the backend already
 * does the naming: `CompanyProfile` is the request body, so an unknown field or one out of
 * bounds is FastAPI's own 422 with a `loc` path. Re-implementing those bounds in the
 * browser would be a second source of truth that drifts the first time a `ge=` moves;
 * this reads the answer instead.
 *
 * `loc` is `['body', <field>]` for a scalar and `['body', 'turnover', 0, 'year']` for a row,
 * so the key is the path after `body`, joined by a dot — `turnover.0.year`. A message with
 * no usable `loc` becomes the form-level error rather than being dropped, because an error
 * nobody can see is worse than one in the wrong place.
 */

export interface FieldErrors {
  /** Keyed by dotted path: `name`, `turnover.0.amount`, `certificates.1.expires_on`. */
  readonly byField: Readonly<Record<string, string>>
  /** Anything that named no field, joined into one sentence. */
  readonly formLevel: string | undefined
}

interface ValidationEntry {
  readonly loc?: readonly (string | number)[]
  readonly msg?: string
}

export const NO_FIELD_ERRORS: FieldErrors = { byField: {}, formLevel: undefined }

export function fieldErrorsFrom(body: unknown): FieldErrors {
  const entries = validationEntries(body)
  if (entries.length === 0) return NO_FIELD_ERRORS

  const byField: Record<string, string> = {}
  const unplaced: string[] = []
  for (const entry of entries) {
    const message = capitalise(entry.msg ?? 'is not valid')
    const path = fieldPath(entry.loc)
    if (path === undefined) unplaced.push(message)
    // First wins: pydantic reports the outermost failure first, and it is the one that
    // describes the field rather than the union member it happened to try.
    else byField[path] ??= message
  }
  return {
    byField,
    formLevel: unplaced.length === 0 ? undefined : unplaced.join(' '),
  }
}

/**
 * The same 422 as one sentence, for a screen that has no field to put it under.
 *
 * `ApiError.detail` uses this for every validation list (audit finding M18): until it did,
 * a list `detail` was `JSON.stringify`ed, and the one screen where a model-level refusal
 * could actually happen — an override reason past `MAX_COMMENT_CHARS` — printed a pydantic
 * array in red. The path is made readable rather than shown raw (`override_reason` →
 * "Override reason", `row_edits.0.override_reason` → "Row edits › 0 › override reason"):
 * the field's own screen-side rules are where a bidder should learn about a limit, so this
 * sentence only ever has to be honest, not pretty. `undefined` when there is nothing to say.
 */
export function describeFieldErrors(errors: FieldErrors): string | undefined {
  const named = Object.entries(errors.byField).map(
    ([path, message]) => `${humanisePath(path)}: ${message}`
  )
  const parts = errors.formLevel === undefined ? named : [...named, errors.formLevel]
  if (parts.length === 0) return undefined
  return parts.map(withoutTrailingStop).join('. ') + '.'
}

const PATH_SEPARATOR = ' › '

/** `row_edits.0.override_reason` → `Row edits › 0 › override reason`. */
function humanisePath(path: string): string {
  return capitalise(path.split('.').join(PATH_SEPARATOR).replaceAll('_', ' '))
}

function withoutTrailingStop(sentence: string): string {
  return sentence.endsWith('.') ? sentence.slice(0, -1) : sentence
}

function validationEntries(body: unknown): readonly ValidationEntry[] {
  if (typeof body !== 'object' || body === null) return []
  const detail = (body as { detail?: unknown }).detail
  return Array.isArray(detail) ? (detail as ValidationEntry[]) : []
}

function fieldPath(loc: readonly (string | number)[] | undefined): string | undefined {
  if (loc === undefined || loc.length < 2 || loc[0] !== 'body') return undefined
  return loc.slice(1).join('.')
}

function capitalise(message: string): string {
  return message.charAt(0).toUpperCase() + message.slice(1)
}
