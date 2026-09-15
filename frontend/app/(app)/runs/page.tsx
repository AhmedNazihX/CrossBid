import type { Metadata } from 'next'

import { DevConsole } from '@/components/dev/dev-console'
import { PageHeader } from '@/components/layout/page-header'

export const metadata: Metadata = {
  title: 'Agent runs · CrossBid',
}

/**
 * The developer console (story S4.6.2), behind the sidebar's Agent runs entry.
 *
 * **Why here and not under Settings.** `/settings` is the bidder's — explanation language
 * and tone live on the company form, and the provider page (bring your own key, S4.6.4) is
 * what that route is reserved for. This screen is the *operator's*: which model answers
 * each role, the temperature, the prompt, the tools, and what each run cost. The
 * placeholder that stood here since S4.1.2 already said per-run cost belongs to the
 * developer console, and the entry already sat in the PLATFORM group beside Company
 * profile and Settings, so the console takes the route it was promised rather than adding
 * a second one. The entry is hidden for anyone the API refuses
 * (`lib/use-developer-access.ts`), so a bidder never sees a door that will not open.
 *
 * No artboard draws this screen (ADR-0034); `components/dev/dev-console.tsx` says which
 * primitives it is built from.
 */
export default function RunsPage() {
  return (
    <>
      <PageHeader
        title="Agent runs"
        description="Tune the agent without touching code — the model behind each role, temperature, max tokens, the system prompt and the tools — and see what every run cost, per node and per bid."
      />
      <DevConsole />
    </>
  )
}
