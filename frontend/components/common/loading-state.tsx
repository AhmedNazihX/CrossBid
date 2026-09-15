/**
 * The waiting line the shell's guards show inside the content frame.
 *
 * No artboard draws a loading state. This is the muted body line the bid workspace already
 * uses for "Loading the bid…", given one home so `RequireSession` and `RequireCompany` cannot
 * drift apart by a class — the two blocks it replaces were the same eight lines twice.
 *
 * **It fills the frame it is rendered in, never the viewport.** The block it replaces was
 * `min-h-dvh` and sat *outside* the shell, so every full load of a protected route painted
 * the window as one centred word with no sidebar and no header (M7 of the 2026-09-15 audit).
 * `app/(app)/layout.tsx` now composes the chrome first and mounts the guards inside the
 * white content frame, which is a `min-h-full` flex column; `flex-1` here is what centres
 * the line in that frame and nothing wider.
 *
 * `role="status"` is a polite live region: a screen reader hears the wait without focus being
 * moved off whatever the person was doing.
 */
export function LoadingState({ message }: Readonly<{ message: string }>) {
  return (
    <div className="flex flex-1 items-center justify-center px-4 py-16">
      <p className="m-0 [font:var(--type-body)] text-text-muted" role="status">
        {message}
      </p>
    </div>
  )
}
