import type { Metadata } from 'next'

import { EmptyState } from '@/components/common/empty-state'
import { PageHeader } from '@/components/layout/page-header'

export const metadata: Metadata = {
  title: 'Settings · CrossBid',
}

/**
 * Placeholder. Explanation language and tone are set on the company form
 * (S4.2.1); the provider page — own OpenAI, Anthropic or OpenRouter key — is
 * S4.6.4 and is Could-priority.
 */
export default function SettingsPage() {
  return (
    <>
      <PageHeader
        title="Settings"
        description="How CrossBid explains itself, and which AI provider answers your bids."
      />
      <EmptyState
        title="No settings to change yet"
        description="This screen is still being built. It will let you choose the language Crossbid explains requirements in, the tone it uses, and — later — bring your own OpenAI, Anthropic or OpenRouter key so the bill and the provider are yours. Until then every bid runs on CrossBid's own provider with the defaults."
        steps={['Nothing to do here today. The defaults are in use.']}
        secondaryAction={{ href: '/dashboard', label: 'Back to dashboard' }}
      />
    </>
  )
}
