'use client'

/**
 * The turnover table of the profile form (story S4.2.1).
 *
 * A repeating row rather than three fixed years: tenders ask for "the last three financial
 * years" but a company founded two years ago has two, and a threshold checked against a
 * year that was never filled in would read as a failed requirement rather than a missing
 * fact. Adding a row is explicit, and removing one is always available.
 *
 * `field_of_activity` is on the row for a reason worth keeping: a selection criterion is
 * routinely "turnover *in the field of the contract*", and a single company-wide figure
 * cannot answer it. The demo pack's `Eigenerklaerung` prints exactly this split.
 *
 * **The rows here are the text the bidder typed, not the numbers.** `TurnoverYear.amount`
 * is a `number`, and a controlled input whose value is the *parsed* number eats the decimal
 * point: `1.` parses to `1`, re-renders as `"1"`, and the next keystroke gives `15` — on the
 * one field most likely to need a decimal. So this component holds strings, never parses,
 * and `profile-form` turns a `TurnoverDraft` into a `TurnoverYear` once, on submit, where
 * text that is not a number can be named under its own field instead of silently becoming
 * `0`. A German bidder's `1500000,50` is accepted there; a thousands separator is not.
 */
import { Button } from '@/components/ui/button'
import { Icon } from '@/components/ui/icons'
import { Input } from '@/components/ui/input'
import type { FieldErrors } from '@/lib/field-errors'

/**
 * One turnover row as the form edits it: `year` and `amount` are the typed text, `''` for
 * a box the bidder has not filled in. `currency` and `field_of_activity` are the saved
 * shapes already.
 */
export interface TurnoverDraft {
  readonly year: string
  readonly amount: string
  readonly currency: string
  readonly field_of_activity: string | null
}

export interface TurnoverRowsProps {
  readonly rows: readonly TurnoverDraft[]
  readonly errors: FieldErrors
  readonly disabled: boolean
  readonly onChange: (rows: readonly TurnoverDraft[]) => void
}

export function TurnoverRows({ rows, errors, disabled, onChange }: TurnoverRowsProps) {
  const update = (index: number, patch: Partial<TurnoverDraft>) =>
    onChange(rows.map((row, at) => (at === index ? { ...row, ...patch } : row)))

  return (
    <div className="flex flex-col gap-3">
      {rows.map((row, index) => (
        <div
          key={index}
          className="grid grid-cols-1 gap-3 rounded-[10px] border border-border-subtle bg-surface-sunken p-3 sm:grid-cols-[7rem_10rem_1fr_auto] sm:items-start"
        >
          <Input
            label="Year"
            inputMode="numeric"
            value={row.year}
            error={errors.byField[`turnover.${index}.year`]}
            disabled={disabled}
            onChange={(event) => update(index, { year: event.target.value })}
          />
          <Input
            label="Amount"
            inputMode="decimal"
            value={row.amount}
            error={errors.byField[`turnover.${index}.amount`]}
            disabled={disabled}
            onChange={(event) => update(index, { amount: event.target.value })}
          />
          <Input
            label="Field of activity"
            hint="Optional. Tenders often ask for turnover in the field of the contract."
            value={row.field_of_activity ?? ''}
            error={errors.byField[`turnover.${index}.field_of_activity`]}
            disabled={disabled}
            onChange={(event) =>
              update(index, { field_of_activity: emptyToNull(event.target.value) })
            }
          />
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="sm:mt-6"
            disabled={disabled}
            onClick={() => onChange(rows.filter((_, at) => at !== index))}
          >
            <Icon name="x" size={16} aria-hidden />
            Remove
            <span className="sr-only"> the turnover row for {row.year || 'this year'}</span>
          </Button>
        </div>
      ))}

      <div>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          disabled={disabled}
          onClick={() => onChange([...rows, nextRow(rows)])}
        >
          Add a financial year
        </Button>
      </div>
    </div>
  )
}

/**
 * The year before the earliest one listed, so three clicks give three consecutive years.
 *
 * `EUR` because every threshold in the golden tenders is in euros and S1.3.1 converts the
 * rest; a currency nobody changes is one fewer field between the bidder and a saved profile.
 *
 * Only a row whose year already reads as a whole number counts towards "earliest": a
 * half-typed year would otherwise seed the next row from garbage.
 */
function nextRow(rows: readonly TurnoverDraft[]): TurnoverDraft {
  const years = rows
    .map((row) => Number(row.year.trim()))
    .filter((year) => Number.isInteger(year) && year > 0)
  const year = years.length === 0 ? new Date().getFullYear() - 1 : Math.min(...years) - 1
  return { year: String(year), amount: '', currency: 'EUR', field_of_activity: null }
}

function emptyToNull(value: string): string | null {
  const trimmed = value.trim()
  return trimmed.length === 0 ? null : trimmed
}
