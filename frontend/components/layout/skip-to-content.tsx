import { MAIN_CONTENT_ID } from './nav-items'

/**
 * Keyboard-only escape from the navigation to the page body. Visually hidden
 * until focused, which is why it cannot use `hidden` or `display: none`.
 */
export function SkipToContent() {
  return (
    <a
      href={`#${MAIN_CONTENT_ID}`}
      className="bg-background text-foreground focus-visible:ring-ring sr-only rounded-lg px-3 py-2 text-sm font-medium shadow-lg focus-visible:not-sr-only focus-visible:absolute focus-visible:top-2 focus-visible:left-2 focus-visible:z-50 focus-visible:ring-3"
    >
      Skip to main content
    </a>
  )
}
