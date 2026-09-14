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
 */
import { Button } from '@/components/ui/button'
import { Icon } from '@/components/ui/icons'
import { Input } from '@/components/ui/input'
import type { TurnoverYear } from '@/lib/companies'
import type { FieldErrors } from '@/lib/field-errors'

export interface TurnoverRowsProps {
  readonly rows: readonly TurnoverYear[]
  readonly errors: FieldErrors
  readonly disabled: boolean
  readonly onChange: (rows: readonly TurnoverYear[]) => void
}

export function TurnoverRows({ rows, errors, disabled, onChange }: TurnoverRowsProps) {
  const update = (index: number, patch: Partial<TurnoverYear>) =>
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
            value={row.year === 0 ? '' : String(row.year)}
            error={errors.byField[`turnover.${index}.year`]}
            disabled={disabled}
            onChange={(event) => update(index, { year: toInteger(event.target.value) })}
          />
          <Input
            label="Amount"
            inputMode="decimal"
            value={row.amount === 0 ? '' : String(row.amount)}
            error={errors.byField[`turnover.${index}.amount`]}
            disabled={disabled}
            onChange={(event) => update(index, { amount: toNumber(event.target.value) })}
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
 */
function nextRow(rows: readonly TurnoverYear[]): TurnoverYear {
  const years = rows.map((row) => row.year).filter((year) => year > 0)
  const year = years.length === 0 ? new Date().getFullYear() - 1 : Math.min(...years) - 1
  return { year, amount: 0, currency: 'EUR', field_of_activity: null }
}

function toInteger(value: string): number {
  const parsed = Number.parseInt(value.replace(/\D/g, ''), 10)
  return Number.isNaN(parsed) ? 0 : parsed
}

function toNumber(value: string): number {
  const parsed = Number.parseFloat(value.replace(/[^\d.,]/g, '').replace(',', '.'))
  return Number.isNaN(parsed) ? 0 : parsed
}

function emptyToNull(value: string): string | null {
  const trimmed = value.trim()
  return trimmed.length === 0 ? null : trimmed
}
