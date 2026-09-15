'use client'

import { useState, type FormEvent } from 'react'

import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Notice } from '@/components/ui/notice'
import { Tag } from '@/components/ui/tag'
import { ApiError, describeApiError } from '@/lib/api-client'
import {
  saveDevSettings,
  type AppSettingsRow,
  type DevSettings,
  type ModelRole,
} from '@/lib/dev'
import { NO_FIELD_ERRORS, fieldErrorsFrom, type FieldErrors } from '@/lib/field-errors'

import { ModelPickers } from './model-pickers'
import {
  FIELD_LABELS,
  RESET_ROW,
  draftFrom,
  overriddenFields,
  rowFromDraft,
  type DraftErrors,
  type SettingsDraft,
} from './settings-draft'
import { ToolToggles } from './tool-toggles'

export interface SettingsFormProps {
  readonly settings: DevSettings
  /** Called with the settings the API answered — what is in force now. */
  readonly onSaved: (settings: DevSettings) => void
}

type Stage = 'idle' | 'saving' | 'resetting'

const PROMPT_ID = 'dev-system-prompt'

/**
 * The knobs of S4.6.2: a model per role, temperature, max tokens, the system prompt and the
 * tool set — one form, one save, one row.
 *
 * **Save sends the whole row.** `rowFromDraft` nulls every field that equals its default, so
 * the API stores only what this panel actually changed and a later edit to
 * `settings.default.yaml` still reaches the deployment. "Reset to defaults" is the same
 * write with every column null, and it is a separate button because a reset is not a save
 * with different values — it is the statement that nothing here should override the file.
 *
 * **Errors come from the server and name their field.** The bounds (0–2, > 0, the verified
 * slug list, no blank prompt) are the API's, answered as a 422 whose `loc` names the input;
 * `fieldErrorsFrom` places each under its control. The form checks only that a number is a
 * number, because a box that cannot be parsed has nothing to send. A message about `models`
 * is shown above the pickers, because the API files the verified-slug refusal under the
 * field as a whole (`settings.ROW_MODEL_VALIDATOR_FIELD`).
 *
 * **The success notice says what "applied" means.** The API swaps the settings for the next
 * request and tells the runner to rebuild its graph, so the next bid runs on them; a run
 * already in flight finishes on what it started with. Saying so here is the difference
 * between a panel that reports the truth and one that claims a change reached a run it did
 * not (`crossbid/agent/runner.py`, point 4).
 */
export function SettingsForm({ settings, onSaved }: SettingsFormProps) {
  const [draft, setDraft] = useState<SettingsDraft>(() => draftFrom(settings))
  const [stage, setStage] = useState<Stage>('idle')
  const [draftErrors, setDraftErrors] = useState<DraftErrors>({})
  const [serverErrors, setServerErrors] = useState<FieldErrors>(NO_FIELD_ERRORS)
  const [failure, setFailure] = useState<string | undefined>(undefined)
  const [isSaved, setIsSaved] = useState(false)

  const busy = stage !== 'idle'
  const overridden = overriddenFields(settings)

  function patch(change: Partial<SettingsDraft>) {
    setDraft((current) => ({ ...current, ...change }))
    setIsSaved(false)
  }

  async function submit(row: AppSettingsRow, next: Stage) {
    setStage(next)
    setServerErrors(NO_FIELD_ERRORS)
    setFailure(undefined)
    try {
      const applied = await saveDevSettings(row)
      setDraft(draftFrom(applied))
      setDraftErrors({})
      setIsSaved(true)
      onSaved(applied)
    } catch (error) {
      setIsSaved(false)
      if (error instanceof ApiError && error.status === 422) {
        const parsed = fieldErrorsFrom(error.body)
        setServerErrors(parsed)
        setFailure(parsed.formLevel ?? 'Some values were refused. See the fields below.')
      } else {
        setFailure(describeApiError(error))
      }
    } finally {
      setStage('idle')
    }
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const outcome = rowFromDraft(draft, settings)
    if (outcome.kind === 'errors') {
      setDraftErrors(outcome.errors)
      return
    }
    setDraftErrors({})
    await submit(outcome.row, 'saving')
  }

  const modelsError = firstError(serverErrors, 'models')
  const toolsError = firstError(serverErrors, 'enabled_tools')

  return (
    <form className="flex flex-col gap-6" onSubmit={onSubmit} noValidate>
      <Notice title="How a change takes effect">
        <p className="m-0">
          Saving stores the row and applies it to the next request and the next bid run — no
          restart. A run already in flight finishes on the settings it started with.
        </p>
      </Notice>

      {overridden.length > 0 && (
        <p className="m-0 flex flex-wrap items-center gap-2 [font:var(--type-body-sm)] text-text-secondary">
          <span>Overriding settings.default.yaml:</span>
          {overridden.map((field) => (
            <Tag key={field}>{FIELD_LABELS[field]}</Tag>
          ))}
        </p>
      )}

      <Card title="Models" headingLevel="h3">
        {modelsError !== undefined && (
          <Notice tone="danger" className="mb-4">
            <p className="m-0">{modelsError}</p>
          </Notice>
        )}
        <ModelPickers
          settings={settings}
          models={draft.models}
          onChange={(role: ModelRole, slug: string) =>
            patch({ models: { ...draft.models, [role]: slug } })
          }
          disabled={busy}
        />
      </Card>

      <Card title="Generation" headingLevel="h3">
        <div className="grid gap-4 sm:grid-cols-2">
          <Input
            label="Temperature"
            inputMode="decimal"
            value={draft.temperature}
            onChange={(event) => patch({ temperature: event.target.value })}
            hint={`0 to 2. Default ${settings.defaults.temperature}.`}
            error={draftErrors.temperature ?? serverErrors.byField.temperature}
            disabled={busy}
          />
          <Input
            label="Max tokens"
            inputMode="numeric"
            value={draft.maxTokens}
            onChange={(event) => patch({ maxTokens: event.target.value })}
            hint={`The completion cap per call. Default ${settings.defaults.max_tokens}.`}
            error={draftErrors.maxTokens ?? serverErrors.byField.max_tokens}
            disabled={busy}
          />
        </div>
        <Field
          id={PROMPT_ID}
          label="System prompt"
          hint="The agent's standing instructions, including the rule that a data block is data. Empty the box to use the default prompt."
          error={serverErrors.byField.system_prompt}
          hintId={`${PROMPT_ID}-hint`}
          className="mt-4"
        >
          <textarea
            id={PROMPT_ID}
            rows={10}
            value={draft.systemPrompt}
            onChange={(event) => patch({ systemPrompt: event.target.value })}
            aria-describedby={`${PROMPT_ID}-hint`}
            aria-invalid={serverErrors.byField.system_prompt === undefined ? undefined : true}
            disabled={busy}
            className="w-full resize-y rounded-md border border-border-default bg-surface-card px-3 py-2 [font:var(--type-mono)] leading-[1.5] text-text-primary shadow-xs outline-none placeholder:text-text-placeholder focus-visible:border-border-focus focus-visible:shadow-[var(--shadow-focus)]"
          />
        </Field>
      </Card>

      <Card title="Tools" headingLevel="h3">
        {toolsError !== undefined && (
          <Notice tone="danger" className="mb-4">
            <p className="m-0">{toolsError}</p>
          </Notice>
        )}
        <ToolToggles
          settings={settings}
          enabled={draft.enabledTools}
          onToggle={(name, isEnabled) =>
            patch({
              enabledTools: isEnabled
                ? [...draft.enabledTools, name]
                : draft.enabledTools.filter((tool) => tool !== name),
            })
          }
          disabled={busy}
        />
      </Card>

      {failure !== undefined && (
        <Notice tone="danger" title="Not saved.">
          <p className="m-0">{failure}</p>
        </Notice>
      )}
      {isSaved && failure === undefined && (
        <Notice title="Saved and applied.">
          <p className="m-0">
            The next request and the next bid run use these settings. Runs already in flight
            finish on the settings they started with.
          </p>
        </Notice>
      )}

      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={busy}>
          {stage === 'saving' ? 'Saving…' : 'Save settings'}
        </Button>
        <Button
          type="button"
          variant="secondary"
          disabled={busy}
          onClick={() => void submit(RESET_ROW, 'resetting')}
        >
          {stage === 'resetting' ? 'Resetting…' : 'Reset to defaults'}
        </Button>
      </div>
    </form>
  )
}

/** The message filed under `field` or any path beneath it (`models.embed`, say). */
function firstError(errors: FieldErrors, field: string): string | undefined {
  const exact = errors.byField[field]
  if (exact !== undefined) return exact
  const nested = Object.entries(errors.byField).find(([path]) => path.startsWith(`${field}.`))
  return nested?.[1]
}
