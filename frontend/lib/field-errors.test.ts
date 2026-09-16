/**
 * `field-errors.ts` — FastAPI's 422 body, placed under the field it names (story S4.2.1).
 *
 * Why this can be quietly wrong: the function never throws. A `loc` it does not understand,
 * a `detail` that is a sentence rather than a list, a message with no `loc` at all — each is
 * a shape FastAPI really sends, and each has a wrong answer that renders as a perfectly
 * calm form with no red text on it. The bidder presses Save again and is refused again,
 * with nothing on the screen saying why. So the bodies below are the real ones: pydantic
 * v2's `{type, loc, msg, input, ctx}` entries as `backend/tests/unit/test_companies_router.py`
 * asserts them (`["body", "country"]`), the nested `["body", "turnover", 0, "year"]` a row
 * produces, and FastAPI's `HTTPException` form `{detail: "..."}`, which is a 422 too but not
 * a validation one.
 */
import { describe, expect, test } from 'vitest'

import { NO_FIELD_ERRORS, fieldErrorsFrom } from './field-errors'

/** `PUT /companies/me` with `staff_fte: -3` — pydantic's `ge=0` answer, verbatim in shape. */
const NEGATIVE_FTE = {
  detail: [
    {
      type: 'greater_than_equal',
      loc: ['body', 'staff_fte'],
      msg: 'Input should be greater than or equal to 0',
      input: -3,
      ctx: { ge: 0 },
    },
  ],
}

describe('fieldErrorsFrom', () => {
  test('a scalar field error lands under its own name, capitalised', () => {
    const errors = fieldErrorsFrom(NEGATIVE_FTE)

    expect(errors.byField).toEqual({ staff_fte: 'Input should be greater than or equal to 0' })
    expect(errors.formLevel).toBeUndefined()
  })

  test('a row field is keyed by its dotted path, index included', () => {
    const body = {
      detail: [
        {
          type: 'greater_than_equal',
          loc: ['body', 'turnover', 0, 'year'],
          msg: 'Input should be greater than or equal to 1900',
          input: 0,
          ctx: { ge: 1900 },
        },
        {
          type: 'date_from_datetime_parsing',
          loc: ['body', 'certificates', 1, 'expires_on'],
          msg: 'Input should be a valid date or datetime, invalid character in year',
          input: 'next year',
        },
      ],
    }

    const { byField } = fieldErrorsFrom(body)

    expect(byField['turnover.0.year']).toBe('Input should be greater than or equal to 1900')
    expect(byField['certificates.1.expires_on']).toBe(
      'Input should be a valid date or datetime, invalid character in year'
    )
  })

  test('the first message for a field wins, because pydantic reports the outer failure first', () => {
    const body = {
      detail: [
        {
          type: 'string_type',
          loc: ['body', 'country'],
          msg: 'Input should be a valid string',
        },
        {
          type: 'string_pattern_mismatch',
          loc: ['body', 'country'],
          msg: 'String should match pattern',
        },
      ],
    }

    expect(fieldErrorsFrom(body).byField).toEqual({ country: 'Input should be a valid string' })
  })

  test('a lower-case pydantic message is capitalised for the screen', () => {
    const body = { detail: [{ loc: ['body', 'name'], msg: 'value is not a valid string' }] }

    expect(fieldErrorsFrom(body).byField.name).toBe('Value is not a valid string')
  })

  test('an entry with no msg still says something under its field', () => {
    const body = { detail: [{ loc: ['body', 'name'] }] }

    expect(fieldErrorsFrom(body).byField.name).toBe('Is not valid')
  })

  test('an error that names no body field becomes the form-level message rather than vanishing', () => {
    const body = {
      detail: [
        { type: 'missing', loc: ['query', 'limit'], msg: 'Field required' },
        { type: 'json_invalid', loc: ['body'], msg: 'JSON decode error' },
        { type: 'missing', msg: 'Field required' },
      ],
    }

    const errors = fieldErrorsFrom(body)

    expect(errors.byField).toEqual({})
    expect(errors.formLevel).toBe('Field required JSON decode error Field required')
  })

  test('a body with field errors and one unplaced error reports both', () => {
    const body = {
      detail: [
        ...NEGATIVE_FTE.detail,
        { type: 'model_type', loc: ['header', 'x-dev-company'], msg: 'Input should be a UUID' },
      ],
    }

    const errors = fieldErrorsFrom(body)

    expect(errors.byField).toEqual({ staff_fte: 'Input should be greater than or equal to 0' })
    expect(errors.formLevel).toBe('Input should be a UUID')
  })

  test.each<[string, unknown]>([
    ['an HTTPException 422 whose detail is a sentence', { detail: 'PUT /companies/me first.' }],
    ['an empty detail list', { detail: [] }],
    ['a body with no detail', { message: 'nope' }],
    ['a string body', 'Internal Server Error'],
    ['undefined', undefined],
    ['null', null],
  ])('%s yields no field errors and no form-level message', (_shape, body) => {
    expect(fieldErrorsFrom(body)).toBe(NO_FIELD_ERRORS)
  })
})
