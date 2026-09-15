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
 * bounds here would be a second source of truth that drifts the first time one moves. The
 * one check the browser does make is the one the server *cannot*: whether a number box
 * holds a number at all, because text that is not one has no `number` to send.
 *
 * **The form edits a draft, and numbers are text until submit.** `staff_fte` and a turnover
 * amount are `number` on the wire, but a controlled input whose value is the parsed number
 * fights the typist: `1.` parses to `1`, re-renders as `"1"`, and the decimal point is gone.
 * So `ProfileDraft` keeps each number as the string the bidder typed, and `profileFrom`
 * turns it into a `CompanyProfile` once, when the form is submitted. A comma is accepted as
 * the decimal mark there — a German bidder types `12,5` — and text that is not a number is
 * named under its own field rather than silently sent as `null` or `0`.
 *
 * **Three outcomes, not two.** `PUT /companies/me` writes the row first and the agent's
 * memory second, and when the second write fails it answers 200 with `warning` set — the
 * profile *was* saved (see the router's docstring: reporting failure for a write that landed
 * is the worse lie). So the outcome is `saved`, `saved_with_warning` or `failed`, and only
 * the last is headed "Not saved". The warning is the same box on the warning tint, headed
 * for what actually happened, with the backend's own sentence saying what to do about it.
 *
 * **Expiry is the backend's verdict, and the response carries it.** `GET /companies/me`
 * returns `has_expired_certificates` and a per-certificate `is_expired`, both judged on
 * `checked_on`, and the router's own field description says "the form warns about it". So
 * the loaded response is kept beside the editable draft — `editableProfile` strips the
 * flags on purpose, they are not request fields — and it drives the notice above the form
 * and the marker on each flagged row. Re-deriving the rule from `expires_on` here would be
 * the second source of truth the paragraph above refuses.
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
import { TurnoverRows, type TurnoverDraft } from '@/components/company/turnover-rows'
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
  type CertificateResponse,
  type CompanyProfile,
  type CompanyProfileResponse,
  type LegalForm,
  type Tone,
} from '@/lib/companies'
import { NAV_ITEMS } from '@/components/layout/nav-items'
import { NO_FIELD_ERRORS, fieldErrorsFrom, type FieldErrors } from '@/lib/field-errors'
import { formatDate } from '@/lib/format'
import { safeNextPath } from '@/lib/safe-next-path'

type Stage = 'loading' | 'ready' | 'saving'

/**
 * What the last load or submit came to. `failed` is the only one headed "Not saved", and it
 * carries its own title because a profile that could not be *loaded* was not "not saved".
 */
type Outcome =
  | { readonly kind: 'none' }
  | { readonly kind: 'saved' }
  | { readonly kind: 'saved_with_warning'; readonly warning: string }
  | { readonly kind: 'failed'; readonly title: string; readonly message: string }

const NO_OUTCOME: Outcome = { kind: 'none' }
const NOT_SAVED = 'Not saved'
const SEE_FIELDS_BELOW = 'Some values need changing. See the fields below.'
const NOT_A_NUMBER = 'Enter a number, such as 12 or 12,5.'

/** The same box `Notice` draws for `tone="danger"`, on the warning tint instead. */
const WARNING_TINT = 'bg-status-warning-bg text-status-warning-text'

/**
 * The profile as the form edits it: `CompanyProfile` with every number held as the text
 * the bidder typed (`''` for an empty box), so the input never re-renders a parsed value
 * back over a half-typed one. `profileFrom` is the only way out of it.
 */
interface ProfileDraft extends Omit<
  CompanyProfile,
  'staff_fte' | 'staff_fte_relevant' | 'turnover'
> {
  readonly staff_fte: string
  readonly staff_fte_relevant: string
  readonly turnover: readonly TurnoverDraft[]
}

export function ProfileForm() {
  const interrupted = useInterruptedDestination()
  const [draft, setDraft] = useState<ProfileDraft>(() => draftFrom(EMPTY_PROFILE))
  const [loaded, setLoaded] = useState<CompanyProfileResponse | undefined>(undefined)
  const [stage, setStage] = useState<Stage>('loading')
  const [errors, setErrors] = useState<FieldErrors>(NO_FIELD_ERRORS)
  const [outcome, setOutcome] = useState<Outcome>(NO_OUTCOME)

  useEffect(() => {
    const controller = new AbortController()
    void (async () => {
      try {
        const { profile: found } = await loadProfile(controller.signal)
        if (controller.signal.aborted) return
        if (found !== undefined) {
          setLoaded(found)
          setDraft(draftFrom(editableProfile(found)))
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          setOutcome({
            kind: 'failed',
            title: 'Your company could not be loaded',
            message: messageOf(error, 'The profile could not be loaded.'),
          })
        }
      } finally {
        if (!controller.signal.aborted) setStage('ready')
      }
    })()
    return () => controller.abort()
  }, [])

  // An edit makes "Saved" untrue, so both saved outcomes clear; a failure stays until the
  // next submit, because the bidder is fixing what it names.
  const patch = useCallback((change: Partial<ProfileDraft>) => {
    setDraft((current) => ({ ...current, ...change }))
    setOutcome((current) => (current.kind === 'failed' ? current : NO_OUTCOME))
  }, [])

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const parsed = profileFrom(draft)
    if ('errors' in parsed) {
      setErrors(parsed.errors)
      setOutcome({ kind: 'failed', title: NOT_SAVED, message: SEE_FIELDS_BELOW })
      return
    }
    setStage('saving')
    setErrors(NO_FIELD_ERRORS)
    setOutcome(NO_OUTCOME)
    try {
      const result = await saveProfile(parsed.profile, { exists: loaded !== undefined })
      setLoaded(result)
      setDraft(draftFrom(editableProfile(result)))
      // The row is written before the agent's memory, and a failure there is a 200 with a
      // `warning` rather than a lost save — so it is the saved outcome with a caveat, never
      // "Not saved" (H14).
      setOutcome(
        result.warning === null || result.warning === undefined
          ? { kind: 'saved' }
          : { kind: 'saved_with_warning', warning: result.warning }
      )
    } catch (error) {
      if (error instanceof ApiError && error.status === 422) {
        const fieldErrors = fieldErrorsFrom(error.body)
        setErrors(fieldErrors)
        setOutcome({
          kind: 'failed',
          title: NOT_SAVED,
          message: fieldErrors.formLevel ?? SEE_FIELDS_BELOW,
        })
      } else {
        setOutcome({
          kind: 'failed',
          title: NOT_SAVED,
          message: messageOf(error, 'The profile could not be saved.'),
        })
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
    return known.some((option) => option.value === draft.country)
      ? known
      : [...known, { value: draft.country, label: draft.country.toUpperCase() }]
  }, [draft.country])

  if (stage === 'loading') {
    return (
      <p className="[font:var(--type-body)] text-text-muted" role="status">
        Loading your company…
      </p>
    )
  }

  const busy = stage === 'saving'
  const exists = loaded !== undefined
  const expired =
    loaded === undefined ? [] : loaded.certificates.filter((held) => held.is_expired)

  const continueLink = interrupted !== undefined && (
    <Button asChild variant="secondary" size="sm" className="mt-3">
      <Link href={interrupted.href}>Continue to {interrupted.label}</Link>
    </Button>
  )

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

      {outcome.kind === 'failed' && (
        <Notice tone="danger" title={outcome.title}>
          {outcome.message}
        </Notice>
      )}

      {outcome.kind === 'saved_with_warning' && (
        <Notice
          role="status"
          title="Saved, but not yet in the agent's memory"
          className={WARNING_TINT}
        >
          <p className="m-0">{outcome.warning}</p>
          {continueLink}
        </Notice>
      )}

      {outcome.kind === 'saved' && (
        <Notice role="status" title="Saved">
          <p className="m-0">
            Your profile is stored and the agent has been told. Checks from now on run against
            it.
          </p>
          {continueLink}
        </Notice>
      )}

      {loaded !== undefined && loaded.has_expired_certificates && (
        <ExpiredCertificatesNotice expired={expired} checkedOn={loaded.checked_on} />
      )}

      <Section title="The company" description="As it appears on the register.">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Input
            label="Legal name"
            required
            className="sm:col-span-2"
            value={draft.name}
            error={errors.byField.name}
            disabled={busy}
            onChange={(event) => patch({ name: event.target.value })}
          />
          <Select
            label="Country"
            hint="Where the company is established"
            options={countryOptions}
            value={draft.country}
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
            value={draft.legal_form}
            error={errors.byField.legal_form}
            disabled={busy}
            onValueChange={(legal_form) => patch({ legal_form })}
          />
          <Input
            label="Registration number"
            hint="Optional — e.g. HRB 84512"
            value={draft.registration_number ?? ''}
            error={errors.byField.registration_number}
            disabled={busy}
            onChange={(event) =>
              patch({ registration_number: emptyToNull(event.target.value) })
            }
          />
          <Input
            label="Register"
            hint="Optional — the court or registry the number belongs to"
            value={draft.registration_court ?? ''}
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
            value={draft.language}
            error={errors.byField.language}
            disabled={busy}
            onValueChange={(language) => patch({ language })}
          />
          <Select<Tone>
            label="Tone"
            options={TONES.map((tone) => ({ value: tone, label: TONE_LABELS[tone] }))}
            value={draft.tone}
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
            value={draft.staff_fte}
            error={errors.byField.staff_fte}
            disabled={busy}
            onChange={(event) => patch({ staff_fte: event.target.value })}
          />
          <Input
            label="FTE in the field of the contract"
            inputMode="decimal"
            hint="Optional"
            value={draft.staff_fte_relevant}
            error={errors.byField.staff_fte_relevant}
            disabled={busy}
            onChange={(event) => patch({ staff_fte_relevant: event.target.value })}
          />
        </div>
      </Section>

      <Section
        title="Turnover"
        description="One row per financial year. Most tenders ask for the last three."
      >
        <TurnoverRows
          rows={draft.turnover}
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
          rows={draft.certificates}
          expired={expired}
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
 * The warning `has_expired_certificates` asks for, said in the backend's own terms: which
 * certificates, judged on which day, and why it matters — `is_expired` is described as
 * "no longer evidence", and `agent/flags.py` puts a reviewer note on every matrix row that
 * cites one (S3.4.4). What to do about it is the two things this form can do.
 */
function ExpiredCertificatesNotice({
  expired,
  checkedOn,
}: Readonly<{ expired: readonly CertificateResponse[]; checkedOn: string }>) {
  const names = expired.map((held) => held.name || 'An unnamed certificate')
  const title =
    names.length === 1 ? `${names[0]} has expired` : `${names.length} certificates have expired`
  return (
    <Notice role="status" title={title} className={WARNING_TINT}>
      <p className="m-0">
        {names.length === 1
          ? 'It was past its expiry date on'
          : `${names.join(', ')} were past their expiry dates on`}{' '}
        {formatDate(checkedOn)}, so the agent no longer counts{' '}
        {names.length === 1 ? 'it' : 'them'} as evidence: every matrix row that cites{' '}
        {names.length === 1 ? 'it' : 'one'} carries a note for the reviewer. Record the renewed
        expiry date below, or remove the row.
      </p>
    </Notice>
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

function messageOf(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

/** The draft the form edits, from the profile as the API holds it. */
function draftFrom(profile: CompanyProfile): ProfileDraft {
  return {
    ...profile,
    staff_fte: numberText(profile.staff_fte),
    staff_fte_relevant: numberText(profile.staff_fte_relevant),
    turnover: profile.turnover.map((row) => ({
      currency: row.currency,
      // The generated schema leaves the field optional; the draft has one shape for "none".
      field_of_activity: row.field_of_activity ?? null,
      year: String(row.year),
      // `0` is what an unfilled amount saves as (see `profileFrom`), so it comes back as
      // the empty box it was, not as a figure the bidder never typed.
      amount: row.amount === 0 ? '' : String(row.amount),
    })),
  }
}

/** The generated schema leaves optional numbers `number | null | undefined`; all three are
 * "not stated", and the input shows the same empty box for each. */
function numberText(value: number | null | undefined): string {
  return value === null || value === undefined ? '' : String(value)
}

type ParsedDraft = { readonly profile: CompanyProfile } | { readonly errors: FieldErrors }

/**
 * The request body from the draft, or the fields that hold text which is not a number.
 *
 * Bounds stay the server's business (a negative FTE is its 422), but a non-number has no
 * `number` to send, so it is the one thing checked here — under the field, in the same
 * shape the server's errors arrive in. An empty optional box is `null`; an empty turnover
 * year or amount is `0`, which the server then names as out of bounds for the year and
 * accepts as a genuine zero for the amount, exactly as before the draft existed.
 */
function profileFrom(draft: ProfileDraft): ParsedDraft {
  const staff_fte = optionalNumber(draft.staff_fte)
  const staff_fte_relevant = optionalNumber(draft.staff_fte_relevant)
  const turnover = draft.turnover.map((row) => ({
    ...row,
    year: optionalNumber(row.year),
    amount: optionalNumber(row.amount),
  }))

  const notNumbers = [
    ...(staff_fte === undefined ? ['staff_fte'] : []),
    ...(staff_fte_relevant === undefined ? ['staff_fte_relevant'] : []),
    ...turnover.flatMap((row, index) => [
      ...(row.year === undefined ? [`turnover.${index}.year`] : []),
      ...(row.amount === undefined ? [`turnover.${index}.amount`] : []),
    ]),
  ]
  if (notNumbers.length > 0) {
    return {
      errors: {
        byField: Object.fromEntries(notNumbers.map((path) => [path, NOT_A_NUMBER])),
        formLevel: undefined,
      },
    }
  }

  return {
    profile: {
      ...draft,
      staff_fte: staff_fte ?? null,
      staff_fte_relevant: staff_fte_relevant ?? null,
      turnover: turnover.map((row) => ({
        ...row,
        year: row.year ?? 0,
        amount: row.amount ?? 0,
      })),
    },
  }
}

/**
 * `null` for an empty box, `undefined` for text that is not a number, the number otherwise.
 *
 * `Number(...)`, not `parseFloat`: `parseFloat('12abc')` is `12`, which would save a value
 * the bidder did not type. A single comma is read as the decimal mark, so `12,5` is `12.5`;
 * `1.500.000,50` is `undefined`, and the field says so rather than guessing.
 */
function optionalNumber(text: string): number | null | undefined {
  const trimmed = text.trim()
  if (trimmed.length === 0) return null
  const parsed = Number(trimmed.replace(',', '.'))
  return Number.isFinite(parsed) ? parsed : undefined
}

function emptyToNull(value: string): string | null {
  const trimmed = value.trim()
  return trimmed.length === 0 ? null : trimmed
}
