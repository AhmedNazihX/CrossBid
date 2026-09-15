/**
 * The developer console's form state, and the row it becomes (story S4.6.2).
 *
 * Pure functions, kept apart from the form so the two rules that matter can be read in one
 * place. **A field equal to its default is not an override.** The row the API stores has a
 * `null` per column meaning "use `settings.default.yaml`", and the panel decides per field
 * whether the value it holds is the default (send `null`) or a change (send the value). Had
 * every field been sent as a value, the first save would have frozen all five at that
 * day's defaults, and a later change to the YAML would never have reached a deployment
 * that once opened this panel. **Numbers live as strings while being typed.** A controlled
 * number input that parsed on every keystroke cannot hold `0.` or an emptied box; the
 * parse happens once, on save, and a value that is not a number is the one thing this
 * module refuses itself — every other bound (0–2, > 0, verified slugs) is the API's 422,
 * which names its field, so the same rule is never written in two places.
 */
import type { AppSettingsRow, DevSettings, ModelRole } from '@/lib/dev'

export interface SettingsDraft {
  /** The switchable roles only; `embed` is never in here (it cannot be switched). */
  readonly models: Readonly<Partial<Record<ModelRole, string>>>
  readonly temperature: string
  readonly maxTokens: string
  readonly systemPrompt: string
  readonly enabledTools: readonly string[]
}

export interface DraftErrors {
  readonly temperature?: string
  readonly maxTokens?: string
}

export type DraftOutcome =
  | { readonly kind: 'row'; readonly row: AppSettingsRow }
  | { readonly kind: 'errors'; readonly errors: DraftErrors }

/** The fields the row may override, in the order the form shows them. */
export type EditableField =
  'models' | 'temperature' | 'max_tokens' | 'system_prompt' | 'enabled_tools'

export function draftFrom(settings: DevSettings): SettingsDraft {
  const models: Partial<Record<ModelRole, string>> = {}
  for (const role of settings.switchable_roles) {
    models[role] = settings.models[role]
  }
  return {
    models,
    temperature: String(settings.temperature),
    maxTokens: String(settings.max_tokens),
    systemPrompt: settings.system_prompt ?? '',
    enabledTools: [
      ...settings.tools.map((tool) => tool.name),
      ...settings.unbuilt_tools,
    ].filter((name) => isEnabled(settings, name)),
  }
}

function isEnabled(settings: DevSettings, name: string): boolean {
  const tool = settings.tools.find((candidate) => candidate.name === name)
  return tool === undefined ? settings.unbuilt_tools.includes(name) : tool.enabled
}

/** The row `PUT /dev/settings` takes, or the two errors this module checks itself. */
export function rowFromDraft(draft: SettingsDraft, settings: DevSettings): DraftOutcome {
  const temperature = parseTemperature(draft.temperature)
  const maxTokens = parseMaxTokens(draft.maxTokens)
  const errors: DraftErrors = {
    ...(temperature === undefined ? { temperature: 'Enter a number, e.g. 0.2.' } : {}),
    ...(maxTokens === undefined ? { maxTokens: 'Enter a whole number, e.g. 16384.' } : {}),
  }
  if (temperature === undefined || maxTokens === undefined) {
    return { kind: 'errors', errors }
  }
  const { defaults } = settings
  const prompt = draft.systemPrompt.trim() === '' ? null : draft.systemPrompt
  return {
    kind: 'row',
    row: {
      models: modelOverrides(draft.models, settings),
      temperature: temperature === defaults.temperature ? null : temperature,
      max_tokens: maxTokens === defaults.max_tokens ? null : maxTokens,
      system_prompt: prompt === defaults.system_prompt ? null : prompt,
      enabled_tools: sameSet(draft.enabledTools, defaults.enabled_tools)
        ? null
        : [...draft.enabledTools].sort(),
    },
  }
}

/** The all-null row: every field back to `settings.default.yaml`. */
export const RESET_ROW: AppSettingsRow = {
  models: null,
  temperature: null,
  max_tokens: null,
  system_prompt: null,
  enabled_tools: null,
}

/** Which fields the settings in force override, for the "overrides in effect" line. */
export function overriddenFields(settings: DevSettings): readonly EditableField[] {
  const { defaults } = settings
  const fields: EditableField[] = []
  if (
    settings.switchable_roles.some((role) => settings.models[role] !== defaults.models[role])
  ) {
    fields.push('models')
  }
  if (settings.temperature !== defaults.temperature) fields.push('temperature')
  if (settings.max_tokens !== defaults.max_tokens) fields.push('max_tokens')
  if (settings.system_prompt !== defaults.system_prompt) fields.push('system_prompt')
  const enabled = settings.tools.filter((tool) => tool.enabled).map((tool) => tool.name)
  if (!sameSet([...enabled, ...settings.unbuilt_tools], defaults.enabled_tools)) {
    fields.push('enabled_tools')
  }
  return fields
}

export const FIELD_LABELS: Readonly<Record<EditableField, string>> = {
  models: 'Models',
  temperature: 'Temperature',
  max_tokens: 'Max tokens',
  system_prompt: 'System prompt',
  enabled_tools: 'Tools',
}

function modelOverrides(
  models: Readonly<Partial<Record<ModelRole, string>>>,
  settings: DevSettings
): AppSettingsRow['models'] {
  const overrides: Partial<Record<ModelRole, string>> = {}
  for (const role of settings.switchable_roles) {
    const slug = models[role]
    if (slug !== undefined && slug !== settings.defaults.models[role]) {
      overrides[role] = slug
    }
  }
  return Object.keys(overrides).length === 0 ? null : overrides
}

function parseTemperature(text: string): number | undefined {
  const trimmed = text.trim()
  if (trimmed === '') return undefined
  const value = Number(trimmed)
  return Number.isFinite(value) ? value : undefined
}

function parseMaxTokens(text: string): number | undefined {
  const trimmed = text.trim()
  if (!/^-?\d+$/.test(trimmed)) return undefined
  return Number(trimmed)
}

function sameSet(left: readonly string[], right: readonly string[]): boolean {
  const a = new Set(left)
  const b = new Set(right)
  return a.size === b.size && [...a].every((name) => b.has(name))
}
