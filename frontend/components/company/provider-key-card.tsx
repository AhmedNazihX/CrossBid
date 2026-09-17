'use client'

import { useCallback, useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Field } from '@/components/ui/field'
import { Notice } from '@/components/ui/notice'
import { Tag } from '@/components/ui/tag'
import { describeApiError } from '@/lib/api-client'
import {
  deleteProviderKey,
  loadProviderKey,
  saveProviderKey,
  type ProviderKeyResponse,
} from '@/lib/provider-keys'

const KEY_INPUT_ID = 'provider-key'
const KEY_HINT_ID = 'provider-key-hint'

type LoadState =
  | { readonly phase: 'loading' }
  | { readonly phase: 'loaded'; readonly key: ProviderKeyResponse | null }
  | { readonly phase: 'failed'; readonly message: string }

/**
 * The company's own OpenRouter key (S5.4, S4.6.4).
 *
 * **Why a bidder has to supply one.** Every token a bid spends is billed to the key that
 * made the call, so the key belongs to the company whose bid it is. There is no shared
 * application key behind this: without a key saved here, uploads and runs are refused with
 * 402 rather than charged to somebody else.
 *
 * **The key is sent once and never comes back.** What this card shows afterwards is the last
 * four characters and when the provider last confirmed it. There is no route that returns a
 * stored key, which is deliberate — see `routers/provider_keys.py`.
 */
export function ProviderKeyCard() {
  const [state, setState] = useState<LoadState>({ phase: 'loading' })
  const [draft, setDraft] = useState('')
  const [isSaving, setIsSaving] = useState(false)
  const [failure, setFailure] = useState<string | undefined>(undefined)

  useEffect(() => {
    const controller = new AbortController()
    loadProviderKey(controller.signal)
      .then((key) => setState({ phase: 'loaded', key }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return
        setState({ phase: 'failed', message: describeApiError(error) })
      })
    return () => controller.abort()
  }, [])

  const save = useCallback(async () => {
    setIsSaving(true)
    setFailure(undefined)
    try {
      const saved = await saveProviderKey(draft.trim())
      setState({ phase: 'loaded', key: saved })
      setDraft('')
    } catch (error) {
      // The provider's judgement, in the API's words: "OpenRouter refused this key", or
      // that it has nothing left to spend. Both are things the bidder fixes here and now.
      setFailure(describeApiError(error))
    } finally {
      setIsSaving(false)
    }
  }, [draft])

  const remove = useCallback(async () => {
    setIsSaving(true)
    setFailure(undefined)
    try {
      await deleteProviderKey()
      setState({ phase: 'loaded', key: null })
    } catch (error) {
      setFailure(describeApiError(error))
    } finally {
      setIsSaving(false)
    }
  }, [])

  return (
    <Card title="Provider key" headingLevel="h2" padding={16}>
      <div className="flex flex-col gap-3">
        <p className="m-0 [font:var(--type-body-sm)] text-text-secondary">
          CrossBid runs this company&rsquo;s bids on this company&rsquo;s own OpenRouter key, so
          the bill is yours and nobody else&rsquo;s. Without one, documents cannot be uploaded
          and bids cannot be started.
        </p>

        {state.phase === 'loading' && (
          <p className="m-0 [font:var(--type-body-sm)] text-text-muted">Loading&hellip;</p>
        )}

        {state.phase === 'failed' && (
          <Notice tone="danger" title="The saved key could not be read">
            {state.message}
          </Notice>
        )}

        {state.phase === 'loaded' && <SavedKey saved={state.key} />}

        {state.phase === 'loaded' && (
          <div className="flex flex-col gap-2">
            <Field
              id={KEY_INPUT_ID}
              hintId={KEY_HINT_ID}
              label={state.key === null ? 'OpenRouter key' : 'Replace the key'}
              hint="Sent once, stored encrypted, and checked with OpenRouter before it is saved. Only the last four characters are ever shown again."
            >
              <input
                id={KEY_INPUT_ID}
                aria-describedby={KEY_HINT_ID}
                type="password"
                autoComplete="off"
                spellCheck={false}
                value={draft}
                placeholder="sk-or-v1-…"
                onChange={(event) => setDraft(event.target.value)}
                className="w-full rounded-sm border border-border-default bg-surface-card px-3 py-2 [font:var(--type-body)]"
              />
            </Field>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                type="button"
                size="sm"
                disabled={isSaving || draft.trim().length === 0}
                onClick={() => void save()}
              >
                {isSaving ? 'Checking…' : 'Save key'}
              </Button>
              {state.key !== null && (
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  disabled={isSaving}
                  onClick={() => void remove()}
                >
                  Remove key
                </Button>
              )}
            </div>
          </div>
        )}

        {failure !== undefined && (
          <Notice tone="danger" title="That key was not saved">
            {failure}
          </Notice>
        )}
      </div>
    </Card>
  )
}

/** What is in force, in the two terms a bidder can check: which key, and when it was last confirmed. */
function SavedKey({ saved }: { saved: ProviderKeyResponse | null }) {
  if (saved === null) {
    return (
      <Notice tone="danger" title="No key saved">
        Until a key is saved, this company cannot upload documents or start a bid.
      </Notice>
    )
  }
  const verified =
    saved.verified_at === null
      ? 'never checked'
      : `checked ${new Date(saved.verified_at).toLocaleDateString()}`
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Tag mono>&hellip;{saved.key_hint}</Tag>
      <span className="[font:var(--type-body-sm)] text-text-secondary">
        OpenRouter key in use &middot; {verified}
      </span>
    </div>
  )
}
