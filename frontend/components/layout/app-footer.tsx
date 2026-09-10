/**
 * Standing reminder of the product's safety boundary. Crossbid is advisory: it
 * never submits a bid, and a human confirms every verdict (docs/project-plan.md,
 * "Settled product decisions"). The claim belongs on every page, so it lives in
 * the shell rather than in one screen.
 */
export function AppFooter() {
  return (
    <footer className="mt-auto border-t">
      <div className="text-muted-foreground mx-auto w-full max-w-5xl px-4 py-6 text-xs">
        Advisory only. Crossbid never submits a bid, and a person confirms or overrides every
        verdict.
      </div>
    </footer>
  )
}
