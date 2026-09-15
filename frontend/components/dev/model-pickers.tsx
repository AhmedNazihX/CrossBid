'use client'

import { Select } from '@/components/ui/select'
import { Tag } from '@/components/ui/tag'
import type { DevSettings, ModelRole } from '@/lib/dev'

export interface ModelPickersProps {
  readonly settings: DevSettings
  readonly models: Readonly<Partial<Record<ModelRole, string>>>
  readonly onChange: (role: ModelRole, slug: string) => void
  readonly disabled?: boolean
}

/**
 * What each role is for, in the words `crossbid/settings.py` uses. The role is the thing
 * a developer picks a model *for*; a picker labelled only "extract" would make them guess.
 */
const ROLE_LABELS: Readonly<Record<ModelRole, string>> = {
  extract: 'Extract — requirements and translation',
  cheap: 'Cheap — classification, chat, injection review',
  embed: 'Embed',
  judge: 'Judge — the evaluation judge',
  fallback: 'Fallback — after a timed-out call and one retry',
}

/**
 * One picker per switchable role, over the verified slugs only (S5.1, ADR-0050).
 *
 * The options are `available_models` — the list of slugs somebody probed with a live call —
 * and not OpenRouter's catalogue, because a slug can be listed there and still be refused
 * by this account's data policy (ADR-0005). The roles come from `switchable_roles`, which is
 * every role but `embed`: its slug is pinned to the stored vectors' width and is shown as a
 * fact rather than offered as a choice. The API refuses an `embed` switch regardless; the
 * absence here is so nobody has to find that out from a 422.
 */
export function ModelPickers({
  settings,
  models,
  onChange,
  disabled = false,
}: ModelPickersProps) {
  const options = settings.available_models.map((slug) => ({ value: slug, label: slug }))
  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-4 sm:grid-cols-2">
        {settings.switchable_roles.map((role) => {
          const current = models[role] ?? settings.models[role]
          const fallback = settings.defaults.models[role]
          return (
            <Select
              key={role}
              label={ROLE_LABELS[role]}
              options={options}
              value={current}
              onValueChange={(slug) => onChange(role, slug)}
              hint={
                current === fallback
                  ? `Default: ${fallback}`
                  : `Overridden — default ${fallback}`
              }
              disabled={disabled}
            />
          )
        })}
      </div>
      <p className="m-0 flex flex-wrap items-center gap-2 [font:var(--type-body-sm)] text-text-muted">
        <span>{ROLE_LABELS.embed}</span>
        <Tag mono>{settings.models.embed}</Tag>
        <span>
          Not switchable: its 1536 dimensions are pinned to the stored vectors, and a different
          model means re-embedding every document.
        </span>
      </p>
    </div>
  )
}
