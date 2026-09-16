/**
 * `ApiError` — what a bidder is shown when the API refuses (S4.2.1, audit finding M18).
 *
 * Why this can be quietly wrong: `detail` is the one string every screen prints verbatim,
 * and FastAPI sends it in two shapes. An `HTTPException` carries a sentence; a request the
 * model refused carries a **list** of pydantic entries. The first is what every screen was
 * built against, so the second went unnoticed until an override reason one character too
 * long produced a red notice reading
 * `[{"type":"string_too_long","loc":["body","override_reason"],…}]`. Nothing threw, the
 * notice was red as designed, and the bidder read JSON. The parser that understands the
 * list already existed (`field-errors.ts`); the constructor just never called it.
 */
import { describe, expect, test } from 'vitest'

import { ApiError, describeApiError } from './api-client'

const URL = 'http://localhost:8000/bids/one/review'

/** `POST /bids/{id}/review` with a 4 001-character `override_reason`, as pydantic answers it. */
const REASON_TOO_LONG = {
  detail: [
    {
      type: 'string_too_long',
      loc: ['body', 'override_reason'],
      msg: 'String should have at most 4000 characters',
      input: 'x'.repeat(4001),
      ctx: { max_length: 4000 },
    },
  ],
}

function validationError(body: unknown): ApiError {
  return new ApiError({
    status: 422,
    statusText: 'Unprocessable Entity',
    method: 'POST',
    url: URL,
    body,
  })
}

describe('ApiError.detail — a validation list is a sentence, never JSON', () => {
  test('names the field and repeats the message', () => {
    const error = validationError(REASON_TOO_LONG)

    expect(error.detail).toBe('Override reason: String should have at most 4000 characters.')
    expect(describeApiError(error)).toBe(error.detail)
  })

  test('never starts with a bracket, whatever the list holds', () => {
    const error = validationError({ detail: [{ msg: 'field required' }] })

    expect(error.detail).toBeDefined()
    expect(error.detail?.startsWith('[')).toBe(false)
    expect(error.detail).toBe('Field required.')
  })

  test('a nested row path reads as a path, not as dotted JSON keys', () => {
    const error = validationError({
      detail: [
        {
          type: 'string_too_long',
          loc: ['body', 'row_edits', 0, 'override_reason'],
          msg: 'String should have at most 4000 characters',
        },
      ],
    })

    expect(error.detail).toBe(
      'Row edits › 0 › override reason: String should have at most 4000 characters.'
    )
  })

  test('the message the constructor builds ends with the same sentence', () => {
    const error = validationError(REASON_TOO_LONG)

    expect(error.message).toBe(
      `POST ${URL} failed with 422 Unprocessable Entity — Override reason: String should have at most 4000 characters.`
    )
  })

  test('a plain sentence detail is still passed through untouched', () => {
    const error = validationError({ detail: 'Override reason is required.' })

    expect(error.detail).toBe('Override reason is required.')
  })
})

describe('ApiError.retryAfterSeconds', () => {
  test('reads a whole-seconds Retry-After', () => {
    const error = new ApiError({
      status: 429,
      statusText: 'Too Many Requests',
      method: 'POST',
      url: URL,
      body: { detail: 'Rate limit reached' },
      headers: new Headers({ 'Retry-After': '120' }),
    })

    expect(error.retryAfterSeconds).toBe(120)
  })

  test('is undefined when the answer carried no header', () => {
    const error = new ApiError({
      status: 429,
      statusText: 'Too Many Requests',
      method: 'POST',
      url: URL,
      body: { detail: 'Rate limit reached' },
      headers: new Headers(),
    })

    expect(error.retryAfterSeconds).toBeUndefined()
  })
})
