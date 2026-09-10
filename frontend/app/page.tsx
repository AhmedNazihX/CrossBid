import Link from 'next/link'

import { Button } from '@/components/ui/button'

// Public landing page. Sign-in lands here in S4.1.1; until then the link below is
// the way into the authenticated shell (S4.1.2).
export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center gap-6 px-6 py-16">
      <div className="flex flex-col gap-2">
        <h1 className="text-4xl font-semibold tracking-tight">Crossbid</h1>
        <p className="text-muted-foreground text-lg">
          Go/no-go qualification for cross-border EU tenders.
        </p>
      </div>

      <p className="text-muted-foreground text-sm leading-relaxed">
        Crossbid reads a tender in the buyer&rsquo;s language, lists what it requires, and
        matches each requirement to your own evidence. It is advisory: it never submits a bid,
        and every matrix cell carries a citation or is marked unclear.
      </p>

      <div>
        <Button asChild size="lg">
          <Link href="/dashboard">Open Crossbid</Link>
        </Button>
      </div>

      <p className="text-muted-foreground text-sm">
        Sign-in, the company profile, the new-bid flow and the bid workspace arrive with stories
        S4.1.1&ndash;S4.5.3. The API runs as a separate process; see{' '}
        <code className="bg-muted rounded px-1.5 py-0.5 font-mono text-xs">
          frontend/README.md
        </code>{' '}
        to start it.
      </p>
    </main>
  )
}
