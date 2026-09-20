/**
 * The questions that cycle through the empty Ask box (ADR-0107).
 *
 * Every one is answerable from a tender pack and none of them needs the bidder's own
 * documents, because the box's job is to show what this thing is *for* — a reader who has
 * never used it learns more from "What is the deadline for questions?" than from "Ask about
 * this tender…". They are English, like the rest of the chrome, while the answers come back in
 * the bidder's language (a settled decision).
 *
 * One constant so the wording is a one-line edit rather than a hunt through JSX.
 */
export const ASK_PLACEHOLDERS: readonly string[] = [
  'What is the deadline for questions?',
  'Which form do I need for subcontractors?',
  'What annual turnover must we prove?',
  'Is a bid bond required?',
  'Which certificates does the buyer accept?',
  'Who is the contracting authority?',
]

/**
 * How long each question rests before the next one replaces it.
 *
 * 3.2 s first, which read as a carousel that had stalled. 2.2 s is long enough to finish the
 * longest of them — "Which certificates does the buyer accept?" — and short enough that the
 * box looks like it is offering rather than waiting.
 */
export const ASK_PLACEHOLDER_INTERVAL_MS = 2_200
/** How long the outgoing question takes to leave, which is `--duration-base`. */
export const ASK_PLACEHOLDER_FADE_MS = 200
