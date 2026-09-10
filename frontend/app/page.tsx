// Placeholder landing page. The real UI (login, dashboard, company, settings,
// bids workspace, dev tools) arrives with stories S4.1-S4.6 in later increments.
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
        This is the scaffold only. The interface — login, dashboard, company
        profile, AI provider settings, and the bid workspace — arrives in later
        increments. Crossbid is advisory: it never submits a bid, and every
        matrix cell carries a citation or is marked unclear.
      </p>

      <p className="text-muted-foreground text-sm">
        The API runs as a separate process. See{" "}
        <code className="bg-muted rounded px-1.5 py-0.5 font-mono text-xs">
          frontend/README.md
        </code>{" "}
        to start it.
      </p>
    </main>
  );
}
