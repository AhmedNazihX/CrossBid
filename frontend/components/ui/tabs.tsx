'use client'

import { useRef, type KeyboardEvent } from 'react'
import { cn } from 'cn'

/**
 * Tabs — `components/core/Tabs.jsx`: the segmented control (ink fill on the selected
 * segment, 38 px, or 44 px `size="lg"` for the phone's Matrix / Source / Verdict switch) and
 * the underline variant (2 px ink rule, muted count after the label). Controlled only. The
 * tablist is keyboard-complete: arrows move between tabs, Home/End jump, and each tab names
 * the panel it controls via `panelId`.
 *
 * The tablist is `shrink-0`. Its callers place it as the first child of a flex column, and
 * the workspace's desktop column is height-capped (`max-h-[calc(100dvh-2rem)]`) so it can
 * scroll internally while sticky. A flex child may shrink to nothing by default, and the
 * tablist has no intrinsic minimum of its own — so at ≥1280 px it was measured at 2 px tall
 * (its borders) with the 38 px tabs clipped behind `overflow-hidden`, and a real click on
 * Source / Ask / Verdict was intercepted for as long as Playwright cared to wait (ADR-0060's
 * control had never worked at the width it was designed for). Refusing to shrink costs the
 * unconstrained columns nothing: they were never asking it to.
 */
export interface TabItem<V extends string> {
  readonly value: V
  readonly label: string
  readonly count?: number
}

export interface TabsProps<V extends string> {
  readonly items: readonly TabItem<V>[]
  readonly value: V
  readonly onChange: (value: V) => void
  readonly variant?: 'segmented' | 'underline'
  readonly size?: 'md' | 'lg'
  readonly fullWidth?: boolean
  /** Accessible name of the tablist, e.g. "Workspace sections". */
  readonly 'aria-label': string
  /**
   * Returns the `id` of the panel a tab controls; the caller renders that panel, and names
   * it back with `aria-labelledby={tabId(panelId(value))}`.
   */
  readonly panelId: (value: V) => string
  readonly className?: string
}

/**
 * The `id` of the tab that controls `panelId` — derived from the panel's own id rather than
 * from a prefix this component makes privately.
 *
 * That is the whole of L3. It used to read `tabId(prefix, value)` where `prefix` was a
 * `useId()` inside `Tabs`, so the ids existed and **no caller could name one**: seven panels
 * across the two workspace layouts carried `role="tabpanel"` and pointed at nothing, and a
 * screen reader entering one announced "tab panel" and stopped. Keying off `panelId`, which
 * the caller already owns and already passes in, needs no new prop and no shared secret, and
 * a panel that renames itself cannot drift from its tab.
 */
export function tabId(panelId: string): string {
  return `${panelId}-tab`
}

export function Tabs<V extends string>({
  items,
  value,
  onChange,
  variant = 'segmented',
  size = 'md',
  fullWidth = false,
  panelId,
  className,
  ...rest
}: TabsProps<V>) {
  const listRef = useRef<HTMLDivElement>(null)

  function focusTab(index: number) {
    const tabs = listRef.current?.querySelectorAll<HTMLButtonElement>('[role="tab"]')
    const target = tabs?.[(index + items.length) % items.length]
    target?.focus()
    const item = items[(index + items.length) % items.length]
    if (item !== undefined) {
      onChange(item.value)
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const keys: Record<string, () => void> = {
      ArrowRight: () => focusTab(index + 1),
      ArrowLeft: () => focusTab(index - 1),
      Home: () => focusTab(0),
      End: () => focusTab(items.length - 1),
    }
    const handler = keys[event.key]
    if (handler !== undefined) {
      event.preventDefault()
      handler()
    }
  }

  const isUnderline = variant === 'underline'
  return (
    <div
      ref={listRef}
      role="tablist"
      aria-label={rest['aria-label']}
      className={cn(
        'shrink-0',
        isUnderline
          ? 'flex gap-6 border-b border-border-default'
          : 'inline-flex overflow-hidden rounded-md border border-border-default bg-surface-card',
        fullWidth && 'flex w-full',
        className
      )}
    >
      {items.map((item, index) => {
        const isSelected = item.value === value
        return (
          <button
            key={item.value}
            type="button"
            role="tab"
            id={tabId(panelId(item.value))}
            aria-selected={isSelected}
            aria-controls={panelId(item.value)}
            tabIndex={isSelected ? 0 : -1}
            onClick={() => onChange(item.value)}
            onKeyDown={(event) => handleKeyDown(event, index)}
            className={cn(
              'text-base font-medium leading-none transition-colors [transition-duration:var(--duration-fast)] focus-visible:relative focus-visible:z-10',
              isUnderline
                ? cn(
                    '-mb-px border-b-2 py-2.5',
                    isSelected
                      ? 'border-blue-500 text-text-primary'
                      : 'border-transparent text-text-muted hover:text-text-primary'
                  )
                : cn(
                    size === 'lg' ? 'h-11' : 'h-[38px]',
                    fullWidth ? 'flex-1 px-2' : 'px-[18px]',
                    isSelected
                      ? 'bg-surface-brand text-white'
                      : 'bg-transparent text-text-primary hover:bg-surface-hover'
                  )
            )}
          >
            {item.label}
            {item.count !== undefined && (
              <span className="ml-1.5 font-normal text-text-muted">{item.count}</span>
            )}
          </button>
        )
      })}
    </div>
  )
}
