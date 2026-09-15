'use client'

import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import type { DevSettings } from '@/lib/dev'

export interface ToolTogglesProps {
  readonly settings: DevSettings
  readonly enabled: readonly string[]
  readonly onToggle: (name: string, isEnabled: boolean) => void
  readonly disabled?: boolean
}

/**
 * Every tool the registry knows, enabled or not (S1.4.1's rule: a panel that listed only the
 * enabled ones could not switch one back on), plus the names configured that no module
 * provides yet — listed so that saving this form cannot silently drop them from the row.
 *
 * `external` is shown because it is the fact a developer weighs before enabling a tool: a
 * call that leaves the process is a call that can be slow, down, or billed. `default` marks
 * what `settings.default.yaml` ships, so a toggle that disagrees with it reads as an
 * override at a glance.
 */
export function ToolToggles({
  settings,
  enabled,
  onToggle,
  disabled = false,
}: ToolTogglesProps) {
  const isOn = (name: string) => enabled.includes(name)
  return (
    <ul className="m-0 flex list-none flex-col gap-3 p-0">
      {settings.tools.map((tool) => (
        <li key={tool.name}>
          <Checkbox
            checked={isOn(tool.name)}
            onChange={(event) => onToggle(tool.name, event.target.checked)}
            disabled={disabled}
            label={
              <span className="inline-flex flex-wrap items-center gap-2">
                <span className="[font:var(--type-mono)]">{tool.name}</span>
                {tool.external && (
                  <Badge tone="neutral" size="sm" dot={false}>
                    external
                  </Badge>
                )}
                {tool.default_enabled !== isOn(tool.name) && (
                  <Badge tone="warning" size="sm" dot={false}>
                    {tool.default_enabled ? 'off — ships on' : 'on — ships off'}
                  </Badge>
                )}
              </span>
            }
            description={tool.description}
          />
        </li>
      ))}
      {settings.unbuilt_tools.map((name) => (
        <li key={name}>
          <Checkbox
            checked={isOn(name)}
            onChange={(event) => onToggle(name, event.target.checked)}
            disabled={disabled}
            label={<span className="[font:var(--type-mono)]">{name}</span>}
            description="Enabled in the settings, but no module provides it yet — a story that has not landed. Left on, it binds nothing."
          />
        </li>
      ))}
    </ul>
  )
}
