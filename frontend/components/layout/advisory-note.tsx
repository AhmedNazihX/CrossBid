/**
 * Standing reminder of the product's safety boundary, kept on every page: CrossBid is
 * advisory, never submits a bid, and a person confirms every verdict (docs/project-plan.md,
 * "Settled product decisions"). Sits where `Shell.jsx` places the account block until
 * sign-in (S4.1.1) puts a person there.
 */
export function AdvisoryNote() {
  return (
    <p className="m-0 px-2.5 [font:var(--type-body-sm)] text-text-muted">
      Advisory by design. CrossBid never submits a bid, and a person confirms or overrides every
      verdict.
    </p>
  )
}
