'use client'

/**
 * The company profile form (story S4.2.1).
 *
 * These are the facts every requirement is checked against, so the screen's job is to make
 * them easy to state and impossible to half-save.
 *
 * **One form, two routes.** A bidder who has just signed in has no company row at all, and
 * every other route answers 404 until one exists (S0.3.1). `lib/companies` decides between
 * `POST /companies` and `PUT /companies/me` from whether the load found one; the person is
 * never asked. The heading and the button change, because "Save" for something that does
 * not exist yet reads as a no-op.
 *
 * **Validation errors come from the server and name their field.** `CompanyProfile` is the
 * request body, so a value out of bounds is FastAPI's own 422 with a `loc` path, and
 * `fieldErrorsFrom` puts each message under the input it belongs to. Re-implementing the
 * bounds here would be a second source of truth that drifts the first time one moves.
 *
 * **Explanation language and tone live here** rather than on a settings page, because the
 * plan puts them here deliberately: brief item Easy 2 (personality and tone) must not
 * depend on the provider page, which is Could-priority and may never be built.
 *
 * **`?next=` is the interrupted journey, and the screen finishes it.** `RequireCompany`
 * sends a bidder here when they asked for somewhere else, and a bounce that says nothing
 * reads as a broken link rather than as a step. So the opening notice names where they were
 * going, and the saved notice offers to take them there — the alternative, redirecting the
 * moment the row exists, would snatch the page away from somebody still filling in their
 * turnover (ADR-0041).
 */
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'

import { CertificateRows } from '@/components/company/certificate-rows'
import { TurnoverRows } from '@/components/company/turnover-rows'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Notice } from '@/components/ui/notice'
import { Select } from '@/components/ui/select'
import { ApiError } from '@/lib/api-client'
import {
  BIDDER_COUNTRIES,
  EMPTY_PROFILE,
  EXPLANATION_LANGUAGES,
  LEGAL_FORMS,
  LEGAL_FORM_LABELS,
  TONES,
  TONE_LABELS,
  editableProfile,
  loadProfile,
  saveProfile,
  type CompanyProfile,
  type LegalForm,
  type Tone,
} from '@/lib/companies'
import { NAV_ITEMS } from '@/components/layout/nav-items'
import { NO_FIELD_ERRORS, fieldErrorsFrom, type FieldErrors } from '@/lib/field-errors'
import { safeNextPath } from '@/lib/safe-next-path'

type Stage = 'loading' | 'ready' | 'saving'

export function ProfileForm() {
  const interrupted = useInterruptedDestination()
  const [profile, setProfile] = useState<CompanyProfile>(EMPTY_PROFILE)
  const [exists, setExists] = useState(false)
  const [stage, setStage] = useState<Stage>('loading')
  const [errors, setErrors] = useState<FieldErrors>(NO_FIELD_ERRORS)
  const [failure, setFailure] = useState<string | undefined>(undefined)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    void (async () => {
      try {
        const { profile: found } = await loadProfile(controller.signal)
        if (controller.signal.aborted) return
        setExists(found !== undefined)
        if (found !== undefined) setProfile(editableProfile(found))
      } catch (error) {
        if (!controller.signal.aborted) setFailure(messageOf(error))
      } finally {
        if (!controller.signal.aborted) setStage('ready')
      }
    })()
    return () => controller.abort()
  }, [])

  const patch = useCallback(
    (change: Partial<CompanyProfile>) => {
      setProfile((current) => ({ ...current, ...change }))
      setSaved(false)
    },
    [setProfile]
  )

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setStage('saving')
    setErrors(NO_FIELD_ERRORS)
    setFailure(undefined)
    try {
      const result = await saveProfile(profile, { exists })
      setProfile(editableProfile(result))
      setExists(true)
      setSaved(true)
      // The agent's memory is written after the row, and a failure there is a 200 with a
      // warning rather than a lost save — so it is shown as a warning, not as an error.
      setFailure(result.warning ?? undefined)
    } catch (error) {
      setSaved(false)
      if (error instanceof ApiError && error.status === 422) {
        const parsed = fieldErrorsFrom(error.body)
        setErrors(parsed)
        setFailure(parsed.formLevel ?? 'Some values need changing. See the fields below.')
      } else {
        setFailure(messageOf(error))
      }
    } finally {
      setStage('ready')
    }
  }

  // A row written by the seed, or one day by a non-EU connector, can hold a country this
  // list does not offer. A controlled `<select>` whose value matches no option renders
  // blank, which reads as "not set" for a field that is set — so the value joins its own
  // list rather than disappearing from it.
  const countryOptions = useMemo(() => {
    const known = BIDDER_COUNTRIES.map((entry) => ({ value: entry.code, label: entry.label }))
    return known.some((option) => option.value === profile.country)
      ? known
      : [...known, { value: profile.country, label: profile.country.toUpperCase() }]
  }, [profile.country])

  if (stage === 'loading') {
    return (
      <p className="[font:var(--type-body)] text-text-muted" role="status">
        Loading your company…
      </p>
    )
  }

  const busy = stage === 'saving'

  return (
    <form className="flex max-w-[52rem] flex-col gap-8" onSubmit={onSubmit} noValidate>
      {!exists && (
        <Notice
          title={
            interrupted === undefined
              ? 'Tell us about your company'
              : `${interrupted.label} needs your company first`
          }
        >
          Crossbid checks every requirement against these facts, so this comes first. You can
          change any of it later.
        </Notice>
      )}

      {failure !== undefined && (
        <Notice tone="danger" title="Not saved">
          {failure}
        </Notice>
      )}

      {saved && failure === undefined && (
        <Notice title="Saved">
          <p className="m-0">
            Your profile is stored and the agent has been told. Checks from now on run against
            it.
          </p>
          {interrupted !== undefined && (
            <Button asChild variant="secondary" size="sm" className="mt-3">
              <Link href={interrupted.href}>Continue to {interrupted.label}</Link>
            </Button>
          )}
        </Notice>
      )}

      <Section title="The company" description="As it appears on the register.">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Input
            label="Legal name"
            required
            className="sm:col-span-2"
            value={profile.name}
            error={errors.byField.name}
            disabled={busy}
            onChange={(event) => patch({ name: event.target.value })}
          />
          <Select
            label="Country"
            hint="Where the company is established"
            options={countryOptions}
            value={profile.country}
            error={errors.byField.country}
            disabled={busy}
            onValueChange={(country) => patch({ country })}
          />
          <Select<LegalForm>
            label="Legal form"
            options={LEGAL_FORMS.map((form) => ({
              value: form,
              label: LEGAL_FORM_LABELS[form],
            }))}
            value={profile.legal_form}
            error={errors.byField.legal_form}
            disabled={busy}
            onValueChange={(legal_form) => patch({ legal_form })}
          />
          <Input
            label="Registration number"
            hint="Optional — e.g. HRB 84512"
            value={profile.registration_number ?? ''}
            error={errors.byField.registration_number}
            disabled={busy}
            onChange={(event) =>
              patch({ registration_number: emptyToNull(event.target.value) })
            }
          />
          <Input
            label="Register"
            hint="Optional — the court or registry the number belongs to"
            value={profile.registration_court ?? ''}
            error={errors.byField.registration_court}
            disabled={busy}
            onChange={(event) => patch({ registration_court: emptyToNull(event.target.value) })}
          />
        </div>
      </Section>

      <Section
        title="How Crossbid writes to you"
        description="Requirements are quoted in the tender's own language and explained in yours."
      >
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Select
            label="Explanation language"
            options={EXPLANATION_LANGUAGES.map((entry) => ({
              value: entry.code,
              label: entry.label,
            }))}
            value={profile.language}
            error={errors.byField.language}
            disabled={busy}
            onValueChange={(language) => patch({ language })}
          />
          <Select<Tone>
            label="Tone"
            options={TONES.map((tone) => ({ value: tone, label: TONE_LABELS[tone] }))}
            value={profile.tone}
            error={errors.byField.tone}
            disabled={busy}
            onValueChange={(tone) => patch({ tone })}
          />
        </div>
      </Section>

      <Section
        title="Staff"
        description="Tenders ask for an average over the last three years, and usually for the field of the contract rather than the whole company."
      >
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Input
            label="Total full-time equivalents"
            inputMode="decimal"
            hint="Optional"
            value={numberValue(profile.staff_fte)}
            error={errors.byField.staff_fte}
            disabled={busy}
            onChange={(event) => patch({ staff_fte: toNullableNumber(event.target.value) })}
          />
          <Input
            label="FTE in the field of the contract"
            inputMode="decimal"
            hint="Optional"
            value={numberValue(profile.staff_fte_relevant)}
            error={errors.byField.staff_fte_relevant}
            disabled={busy}
            onChange={(event) =>
              patch({ staff_fte_relevant: toNullableNumber(event.target.value) })
            }
          />
        </div>
      </Section>

      <Section
        title="Turnover"
        description="One row per financial year. Most tenders ask for the last three."
      >
        <TurnoverRows
          rows={profile.turnover}
          errors={errors}
          disabled={busy}
          onChange={(turnover) => patch({ turnover: [...turnover] })}
        />
      </Section>

      <Section
        title="Certificates"
        description="What you hold. The documents that prove it are uploaded below."
      >
        <CertificateRows
          rows={profile.certificates}
          errors={errors}
          disabled={busy}
          onChange={(certificates) => patch({ certificates: [...certificates] })}
        />
      </Section>

      <div className="flex items-center gap-3">
        <Button type="submit" disabled={busy}>
          {busy ? 'Saving…' : exists ? 'Save changes' : 'Create my company'}
        </Button>
      </div>
    </form>
  )
}

function Section({
  title,
  description,
  children,
}: Readonly<{ title: string; description: string; children: React.ReactNode }>) {
  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h2 className="m-0 text-[length:var(--text-md)] font-semibold text-text-primary">
          {title}
        </h2>
        <p className="m-0 [font:var(--type-body-sm)] text-text-secondary">{description}</p>
      </div>
      {children}
    </section>
  )
}

/**
 * Where `RequireCompany` was taking the bidder when it sent them here, if it did.
 *
 * Named from the nav rather than from the path, so the notice says "Dashboard" and not
 * "/dashboard" — and `undefined` for a path no nav entry claims, because inventing a label
 * for an unknown destination is how a reassuring sentence becomes a wrong one.
 */
function useInterruptedDestination():
  { readonly href: string; readonly label: string } | undefined {
  const requested = useSearchParams().get('next')
  if (requested === null) return undefined
  const href = safeNextPath(requested)
  const item = NAV_ITEMS.find((entry) => entry.href === href)
  return item === undefined ? undefined : { href, label: item.label }
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : 'The profile could not be loaded.'
}

/** The generated schema leaves optional numbers `number | null | undefined`; all three are
 * "not stated", and the input shows the same empty box for each. */
function numberValue(value: number | null | undefined): string {
  return value === null || value === undefined ? '' : String(value)
}

function toNullableNumber(value: string): number | null {
  const trimmed = value.trim()
  if (trimmed.length === 0) return null
  const parsed = Number.parseFloat(trimmed.replace(',', '.'))
  return Number.isNaN(parsed) ? null : parsed
}

function emptyToNull(value: string): string | null {
  const trimmed = value.trim()
  return trimmed.length === 0 ? null : trimmed
}
