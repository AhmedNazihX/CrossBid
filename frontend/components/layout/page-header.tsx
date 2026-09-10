/**
 * The one heading every shell page opens with: an `h1` plus a plain-English line
 * saying what the page is for. Keeps the `h1` per page at exactly one.
 */
export function PageHeader({
  title,
  description,
}: Readonly<{ title: string; description: string }>) {
  return (
    <div className="flex flex-col gap-1">
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      <p className="text-muted-foreground text-sm">{description}</p>
    </div>
  )
}
