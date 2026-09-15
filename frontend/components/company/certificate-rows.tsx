'use client'

/**
 * The certificates the company holds (story S4.2.1).
 *
 * **Every field but the name is optional, and the dates are the reason.** A bidder knows
 * they hold ISO 27001 long before they can find the certificate number, and a form that
 * demanded all six fields would be answered with invented ones. What the agent needs first
 * is the name — `company_rag_search` retrieves the evidence document itself.
 *
 * **`expires_on` earns its own hint.** S2.4.1 flags an expired certificate on the profile,
 * and a certificate with no expiry recorded is *not* the same as a valid one: the response
 * model reports `is_valid: false` for it, because without a date the profile cannot claim
 * validity. The hint says so, so that leaving it blank is a decision rather than an omission.
 *
 * **The "Expired" marker is the backend's verdict, not this component's.** `is_expired` is
 * computed by `GET /companies/me` against `checked_on`, and re-deriving the rule here would
 * be a second definition of "expired" that drifts from `CertificateHeld.is_expired_on`. So
 * the form passes down the certificates the last load or save flagged, and a row wears the
 * marker while it still matches one by name and expiry date. Change the date and the marker
 * goes — the backend has not judged the new date yet, and the next save will.
 */
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Icon } from '@/components/ui/icons'
import { Input } from '@/components/ui/input'
import type { CertificateHeld, CertificateResponse } from '@/lib/companies'
import type { FieldErrors } from '@/lib/field-errors'
import { formatDate } from '@/lib/format'

export interface CertificateRowsProps {
  readonly rows: readonly CertificateHeld[]
  /** The certificates the API flagged `is_expired` on its last read or save. */
  readonly expired: readonly CertificateResponse[]
  readonly errors: FieldErrors
  readonly disabled: boolean
  readonly onChange: (rows: readonly CertificateHeld[]) => void
}

const EMPTY_CERTIFICATE: CertificateHeld = {
  name: '',
  issuer: null,
  number: null,
  issued_on: null,
  expires_on: null,
  scope: null,
}

const EXPIRY_HINT =
  'Left blank, the profile cannot claim it is valid — which is not the same as expired.'

export function CertificateRows({
  rows,
  expired,
  errors,
  disabled,
  onChange,
}: CertificateRowsProps) {
  const update = (index: number, patch: Partial<CertificateHeld>) =>
    onChange(rows.map((row, at) => (at === index ? { ...row, ...patch } : row)))

  return (
    <div className="flex flex-col gap-3">
      {rows.map((row, index) => {
        const isExpired = wasFlaggedExpired(row, expired)
        return (
          <div
            key={index}
            className="flex flex-col gap-3 rounded-[10px] border border-border-subtle bg-surface-sunken p-3"
          >
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-[1fr_auto] sm:items-start">
              <Input
                label="Certificate"
                placeholder="ISO/IEC 27001:2022"
                value={row.name}
                error={errors.byField[`certificates.${index}.name`]}
                disabled={disabled}
                onChange={(event) => update(index, { name: event.target.value })}
              />
              <div className="flex items-center gap-2 sm:mt-6">
                {isExpired && (
                  <Badge tone="warning" size="sm">
                    Expired
                  </Badge>
                )}
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  disabled={disabled}
                  onClick={() => onChange(rows.filter((_, at) => at !== index))}
                >
                  <Icon name="x" size={16} aria-hidden />
                  Remove
                  <span className="sr-only"> {row.name || 'this certificate'}</span>
                </Button>
              </div>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <Input
                label="Issued by"
                hint="Optional"
                value={row.issuer ?? ''}
                error={errors.byField[`certificates.${index}.issuer`]}
                disabled={disabled}
                onChange={(event) => update(index, { issuer: emptyToNull(event.target.value) })}
              />
              <Input
                label="Certificate number"
                hint="Optional"
                value={row.number ?? ''}
                error={errors.byField[`certificates.${index}.number`]}
                disabled={disabled}
                onChange={(event) => update(index, { number: emptyToNull(event.target.value) })}
              />
              <Input
                label="Issued on"
                type="date"
                hint="Optional"
                value={row.issued_on ?? ''}
                error={errors.byField[`certificates.${index}.issued_on`]}
                disabled={disabled}
                onChange={(event) =>
                  update(index, { issued_on: emptyToNull(event.target.value) })
                }
              />
              <Input
                label="Expires on"
                type="date"
                hint={
                  isExpired
                    ? `Expired on ${formatDate(row.expires_on)} — no longer evidence.`
                    : EXPIRY_HINT
                }
                value={row.expires_on ?? ''}
                error={errors.byField[`certificates.${index}.expires_on`]}
                disabled={disabled}
                onChange={(event) =>
                  update(index, { expires_on: emptyToNull(event.target.value) })
                }
              />
            </div>
          </div>
        )
      })}

      <div>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          disabled={disabled}
          onClick={() => onChange([...rows, EMPTY_CERTIFICATE])}
        >
          Add a certificate
        </Button>
      </div>
    </div>
  )
}

/**
 * Whether the API flagged this row expired, matched on name and expiry date.
 *
 * Not by index: the bidder can remove a row above this one before saving, and an index
 * would then pin the marker to the wrong certificate. Name plus date is the pair that
 * decides expiry, so a row that still matches is still the one that was judged.
 */
function wasFlaggedExpired(
  row: CertificateHeld,
  expired: readonly CertificateResponse[]
): boolean {
  return expired.some((held) => held.name === row.name && held.expires_on === row.expires_on)
}

function emptyToNull(value: string): string | null {
  const trimmed = value.trim()
  return trimmed.length === 0 ? null : trimmed
}
