'use client'

import { useCallback, useEffect, useState } from 'react'

import { EmptyState } from '@/components/common/empty-state'
import { Eyebrow } from '@/components/ui/eyebrow'
import { Notice } from '@/components/ui/notice'
import { ApiError, describeApiError } from '@/lib/api-client'
import { loadDevCosts, loadDevSettings, type DevCosts, type DevSettings } from '@/lib/dev'

import { CostReport } from './cost-report'
import { SettingsForm } from './settings-form'

type Stage = 'loading' | 'denied' | 'failed' | 'ready'

/** The API's two ways of saying "not for you": off the developer list, or in production. */
const DENYING_STATUSES: ReadonlySet<number> = new Set([401, 403, 404])

/**
 * The developer console (story S4.6.2; graded Medium 7 and Medium 8): the settings form
 * and the cost report on one screen, behind the API's own gate.
 *
 * **There is no artboard for this screen, and that is recorded rather than quietly done
 * (ADR-0034).** The canvas draws the bidder's six screens; an operator's panel was never
 * among them. Like `components/auth/sign-in-card.tsx` and `components/matrix/row-feedback.tsx`
 * it is assembled from the primitives the artboards already fixed — `Card`, `Select`,
 * `Input`, `Checkbox`, `Notice`, `MetricCard`, `DataTable`, `Tag`, `Badge`, `Button` — and
 * invents no spacing, colour or type of its own.
 *
 * **The gate is the server's.** The browser has no idea whether this account is on
 * `DEVELOPER_EMAILS`; it asks `GET /dev/settings`, and a 403 or a 404 (a production API has
 * no `/dev/*` routes at all) renders the refusal below instead of the console. The same
 * answer hides the sidebar entry (`lib/use-developer-access.ts`). The settings are loaded
 * first because they are the gate; the costs follow, and a failure there is a notice in
 * the cost section rather than a screen that refuses to tune anything because a report
 * would not load. After a save the settings shown are the ones the API answered — what is
 * in force — never the form's own idea of them.
 */
export function DevConsole() {
  const [stage, setStage] = useState<Stage>('loading')
  const [settings, setSettings] = useState<DevSettings | undefined>(undefined)
  const [failure, setFailure] = useState<string | undefined>(undefined)
  const [costs, setCosts] = useState<DevCosts | undefined>(undefined)
  const [costsError, setCostsError] = useState<string | undefined>(undefined)
  const [isLoadingCosts, setIsLoadingCosts] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    void (async () => {
      try {
        const loaded = await loadDevSettings(controller.signal)
        if (controller.signal.aborted) return
        setSettings(loaded)
        setStage('ready')
      } catch (error) {
        if (controller.signal.aborted) return
        if (error instanceof ApiError && DENYING_STATUSES.has(error.status)) {
          setStage('denied')
        } else {
          setFailure(describeApiError(error))
          setStage('failed')
        }
      }
    })()
    return () => controller.abort()
  }, [])

  const refreshCosts = useCallback(async (signal?: AbortSignal) => {
    setIsLoadingCosts(true)
    setCostsError(undefined)
    try {
      const report = await loadDevCosts(signal)
      if (signal?.aborted) return
      setCosts(report)
    } catch (error) {
      if (signal?.aborted) return
      setCostsError(describeApiError(error))
    } finally {
      if (!signal?.aborted) setIsLoadingCosts(false)
    }
  }, [])

  useEffect(() => {
    if (stage !== 'ready') return
    const controller = new AbortController()
    void refreshCosts(controller.signal)
    return () => controller.abort()
  }, [stage, refreshCosts])

  if (stage === 'loading') {
    return (
      <p className="m-0 [font:var(--type-body)] text-text-muted" role="status">
        Checking who is asking…
      </p>
    )
  }

  if (stage === 'denied') {
    return (
      <EmptyState
        title="This console is for developers"
        description="The developer console is open to accounts on the API's developer list, and only outside production. Your account is not on it, or this API has the console switched off."
        secondaryAction={{ href: '/dashboard', label: 'Back to dashboard' }}
      />
    )
  }

  if (stage === 'failed' || settings === undefined) {
    return (
      <Notice tone="danger" title="The console could not be loaded.">
        <p className="m-0">{failure ?? 'Something went wrong. Try again.'}</p>
      </Notice>
    )
  }

  return (
    <div className="flex flex-col gap-10">
      <section aria-labelledby="dev-settings-heading" className="flex flex-col gap-4">
        <Eyebrow id="dev-settings-heading">Agent settings</Eyebrow>
        <SettingsForm settings={settings} onSaved={setSettings} />
      </section>

      <section aria-labelledby="dev-costs-heading" className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Eyebrow id="dev-costs-heading">What the runs cost</Eyebrow>
          <button
            type="button"
            className="text-sm font-medium text-text-secondary underline-offset-2 hover:underline disabled:opacity-50"
            onClick={() => void refreshCosts()}
            disabled={isLoadingCosts}
          >
            Refresh
          </button>
        </div>
        <CostReport
          costs={costs}
          error={costsError}
          isLoading={isLoadingCosts && costs === undefined}
        />
      </section>
    </div>
  )
}
