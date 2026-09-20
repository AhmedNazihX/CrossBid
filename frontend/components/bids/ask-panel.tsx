'use client'

import {
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from 'react'
import { cn } from 'cn'

import type { Citation } from '@/components/matrix/citation'
import { EvidenceList } from '@/components/matrix/evidence-list'
import { FeedbackControls } from '@/components/matrix/row-feedback'
import { answerTarget, type RowFeedbackController } from '@/components/matrix/use-row-feedback'
import { Button } from '@/components/ui/button'
import { Eyebrow } from '@/components/ui/eyebrow'
import { Icon } from '@/components/ui/icons'
import { Notice } from '@/components/ui/notice'
import { MAX_QUESTION_CHARS, type ChatTurn } from '@/lib/chat'
import { formatTime } from '@/lib/format'
import { useRotatingPlaceholder } from './use-rotating-placeholder'
import type { BidChatController, ChatExchange } from './use-bid-chat'

export interface AskPanelProps {
  readonly chat: BidChatController
  /** The workspace's one feedback controller — the same map the matrix rows rate into (S4.6.3). */
  readonly feedback: RowFeedbackController
  /** The language the answers arrive in — `lang` on every answer, for the screen reader. */
  readonly bidderLanguage: string
  readonly activeCitation: Citation | undefined
  /** The workspace's citation handler — the same one the matrix uses, so a cited page opens the same way. */
  readonly onCite: (citation: Citation) => void
  /**
   * `phone` fills the Ask tab with 40 px controls; `banner` is the card above the requirements
   * matrix on the desktop (ADR-0104), and is the variant whose turn log has a scroller of its
   * own. There is no third: the `panel` variant died with ADR-0104's side column.
   */
  readonly variant?: 'phone' | 'banner'
}

/**
 * "Ask the tender" — one question in, one cited answer out, over `POST /bids/{id}/chat`
 * (story S4.6.1 on ADR-0055).
 *
 * **What it implements, and what has no artboard.** The ask bar of `Dashboard.dc.html` is
 * the artboard for the question box — a search glyph, an unadorned field and an action row
 * inside one bordered, `--shadow-xs` box — and that bar is now the whole of this component's
 * chrome: ADR-0110 took away the `Card` that used to wrap it, which had put a bordered box
 * inside a bordered box. The log of turns under it has no artboard: the canvas of ADR-0014
 * predates the route. So, like `row-feedback.tsx`, it is assembled from primitives the
 * artboards already fixed — `Eyebrow`, the matrix's own `EvidenceList` and `Notice`,
 * `Button` — and invents no spacing, colour or type of its own.
 *
 * **The box is at the top and the newest exchange is under it.** This card sits in the
 * page's flow with no scroller of its own, so a chat that grows upward from a bottom-pinned
 * input would push that input off the screen with every answer. Anchored at the top, the
 * question box never moves, the answer lands directly beneath the words the bidder just
 * typed, and earlier turns fall away downward. It is also the shape the ask bar has on the
 * dashboard: the bar, then what came of it.
 *
 * **The `banner` variant is the one exception, and it is the reason for the paragraph above
 * rather than a contradiction of it.** Since ADR-0104 the desktop puts this card *above* the
 * requirements matrix instead of in a tabbed side column, which is where a bidder looks for
 * it — but "turns fall away downward" then means they fall away *onto the matrix*, pushing
 * the rows the bidder came for off the screen one answer at a time. So in `banner`, and only
 * there, the log gets a bounded scroller. The question box stays outside it, so the thing
 * that must never move still never moves; what is bounded is the history, which is the part
 * a bidder scrolls on purpose.
 *
 * **Only this session's exchanges are shown, and the panel says so.** The server keeps the
 * thread, so a follow-up question reaches an agent that remembers the last one, but no route
 * reads that thread back (`use-bid-chat.ts`). A log that started full on reload would need
 * a route this story does not have; a log that starts empty and admits the agent remembers
 * more is the honest one.
 *
 * **Uncited is visible at a glance.** A cited answer carries its pages as `CitationLink`s
 * under a "Sources" eyebrow — the same face and the same jump as a matrix row's evidence.
 * An answer with `citations: []` gets a sunken `Notice` with the alert glyph instead, saying
 * nothing behind it was checked. The server already ends such an answer with its own fixed
 * sentence (and answers a fixed refusal when nothing was retrieved at all); the notice is
 * not a paraphrase of that sentence but the visual difference the sentence alone lacks when
 * a German paragraph is skimmed. Both cases are keyed on the empty list the API sent, never
 * on matching the sentence's text.
 *
 * **Every answer can be rated, and the panel is honest about where the rating goes.** Story
 * S4.6.3 reads "rate a matrix row *or chat answer*", and the API's second target — a
 * `matrix_row_id` of `null`, "the bid's own answer" (`routers/feedback.py`, ADR-0051) — is
 * what an answer rates. The thumbs are `FeedbackControls`, the same piece as under a matrix
 * row, keyed per exchange by `answerTarget` so a bidder who rates the first answer up and
 * the second down sees both thumbs where they put them. The API, though, cannot tell two
 * answers of one bid apart, so the "kept" line says the record holds the thumb and the
 * comment but not which answer they were about — rather than "Kept with this answer", which
 * would be untrue. Rating only the newest answer was the alternative and was worse: all
 * answers share one server key, so the moment a new answer arrived it would have inherited
 * the previous one's chosen thumb (`use-row-feedback.ts` has the whole decision).
 *
 * **While a question is in flight, the box stays open and only sending is refused.** The
 * field is not disabled — disabling it would throw focus to the body and stop the bidder
 * typing the next question — but the button is, Enter is ignored, and the controller's ref
 * refuses a second call regardless. The pending exchange reads "Asking…" in the log, which
 * is a `role="log"` live region, so a screen reader hears the answer arrive without the
 * page's status line being borrowed for a German paragraph.
 *
 * **A 429 says when.** When the browser can read `Retry-After`, the form is disabled until
 * that second and the hint names the clock time; when it cannot (the API exposes the header
 * through CORS, but a proxy may strip it), the API's own sentence — which carries the same
 * number of seconds — is shown verbatim under the question, the way
 * `sign-in-card.tsx` shows Supabase's rate-limit text rather than "something went wrong".
 */
/** About five rows; past it the box scrolls rather than eating the page. */
const MAX_BOX_HEIGHT_PX = 132

export function AskPanel({
  chat,
  feedback,
  bidderLanguage,
  activeCitation,
  onCite,
  variant = 'banner',
}: AskPanelProps) {
  const [draft, setDraft] = useState('')
  const boxRef = useRef<HTMLTextAreaElement>(null)
  const fieldId = useId()
  const headingId = `${fieldId}-heading`
  const hintId = `${fieldId}-hint`
  const isPhone = variant === 'phone'
  const isBanner = variant === 'banner'
  const isBlocked = chat.blockedUntil !== undefined
  // Paused the moment there is something to read in the box, and while sending.
  const placeholder = useRotatingPlaceholder(draft !== '' || chat.isAsking)
  const canSend = draft.trim() !== '' && !chat.isAsking && !isBlocked
  const newestFirst = [...chat.exchanges].reverse()

  /**
   * The box is one line at rest and grows with the question.
   *
   * It was `rows={2}`, which spent a line of height on a box that is empty almost all of the
   * time — and this card sits directly above the matrix, so it paid that on every bid. Two
   * details matter: the height is reset to `0px` before `scrollHeight` is read, because
   * `scrollHeight` on an already-tall box reports the old height and the box could then only
   * ever grow; and this is `useLayoutEffect`, so the box is never painted at the wrong size.
   * Clearing the draft after a send collapses it again for free.
   *
   * The first auto-growing textarea in this repo — there was no helper to reuse.
   */
  useLayoutEffect(() => {
    const box = boxRef.current
    if (box === null) {
      return
    }
    box.style.height = '0px'
    box.style.height = `${Math.min(box.scrollHeight, MAX_BOX_HEIGHT_PX)}px`
  }, [draft])

  async function send() {
    if (!canSend) {
      return
    }
    const question = draft
    setDraft('')
    await chat.ask(question)
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void send()
  }

  // Enter sends and Shift+Enter breaks the line, as in every chat box a bidder has used;
  // a composing IME's Enter commits the character, not the question.
  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      void send()
    }
  }

  // One line. What this used to also say — where answers come from and that they carry their
  // page — now sits in the empty state, which is where a first-time reader is and where there
  // is room for it. The rate-limit sentence is the one case worth a second line.
  const hint =
    chat.blockedUntil !== undefined
      ? `This company has used its hour's questions. Ask again at ${formatTime(new Date(chat.blockedUntil))}.`
      : 'Enter sends · Shift+Enter for a new line'

  return (
    // No card and no visible title (ADR-0110). The composer already carries a border, so a
    // second frame around it was a box inside a box, and "Ask the tender" over a field whose
    // own placeholder asks a question was a label for something that labels itself.
    //
    // **The heading is kept, not deleted.** `Card` rendered its title as a real `h2`, which is
    // how heading navigation reached this part of the page; dropping the chrome must not drop
    // that, so the heading stays `sr-only` and names the region through `aria-labelledby`.
    <section aria-labelledby={headingId} className="min-w-0">
      <h2 id={headingId} className="sr-only">
        Ask the tender
      </h2>
      <form
        onSubmit={handleSubmit}
        className={cn(
          'rounded-[14px] border border-border-default bg-surface-card px-4 pt-3 pb-2.5 shadow-xs transition-shadow [transition-duration:var(--duration-fast)]',
          'focus-within:border-border-focus focus-within:shadow-[var(--shadow-focus)] focus-within:focus-ring'
        )}
      >
        <label htmlFor={fieldId} className="sr-only">
          Your question about this tender
        </label>
        <div className="flex items-start gap-3">
          <Icon name="search" size={20} className="mt-1.5 shrink-0 text-text-muted" />
          <div className="relative min-w-0 flex-1">
            <textarea
              ref={boxRef}
              id={fieldId}
              rows={1}
              value={draft}
              maxLength={MAX_QUESTION_CHARS}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={handleKeyDown}
              aria-describedby={hintId}
              className="block w-full min-w-0 resize-none overflow-y-auto bg-transparent py-1.5 text-base leading-[1.5] text-text-primary outline-none"
            />
            {/* The rotating question, drawn over the empty field rather than set as its
                `placeholder`, because a `placeholder` attribute cannot animate. It is
                `aria-hidden` and not focusable: the box is named by its `<label>`, which never
                changes, so nothing a screen reader reads is moving. */}
            {draft === '' && (
              <span
                aria-hidden="true"
                data-testid="ask-placeholder"
                className="pointer-events-none absolute inset-x-0 top-1.5 block truncate text-base leading-[1.5] text-text-placeholder"
              >
                <span
                  key={placeholder.key}
                  className={cn(
                    'block truncate',
                    placeholder.isLeaving
                      ? 'motion-safe:animate-[ask-placeholder-out_200ms_var(--ease-out)_forwards]'
                      : 'motion-safe:animate-[ask-placeholder-in_240ms_var(--ease-out)]'
                  )}
                >
                  {placeholder.text}
                </span>
              </span>
            )}
          </div>
        </div>
        <div className="mt-2.5 flex items-end justify-between gap-3">
          <p
            id={hintId}
            className={cn(
              'm-0 [font:var(--type-body-sm)]',
              isBlocked ? 'text-text-secondary' : 'text-text-muted'
            )}
          >
            {hint}
          </p>
          {/* Icon-only and round, so the toolbar row reads as a bar rather than as a second
              sentence. It keeps a real name for anyone who cannot see the arrow. */}
          <Button
            type="submit"
            shape="circle"
            size={isPhone ? 'md' : 'sm'}
            disabled={!canSend}
            aria-label={chat.isAsking ? 'Asking…' : 'Ask the tender'}
          >
            <Icon name="arrow" size={16} />
          </Button>
        </div>
      </form>

      {newestFirst.length === 0 ? (
        <p className="m-0 mt-3 [font:var(--type-body-sm)] text-text-secondary">
          Answered from this tender, your documents and the matrix — in your language, with the
          page it came from. Only this tab&rsquo;s questions are listed, though the bid keeps
          the thread.
        </p>
      ) : (
        // The live region wraps the list rather than being the list: `role="log"` on the
        // `<ol>` itself would replace its list role and orphan every `<li>` for a reader.
        <div
          role="log"
          aria-label="Questions and answers"
          className={cn('mt-5', isBanner && 'max-h-[360px] overflow-y-auto pr-1')}
        >
          <ol className="m-0 flex list-none flex-col gap-5 p-0">
            {newestFirst.map((exchange) => (
              <li key={exchange.id} className="min-w-0 border-t border-border-default pt-4">
                <Exchange
                  exchange={exchange}
                  feedback={feedback}
                  bidderLanguage={bidderLanguage}
                  activeCitation={activeCitation}
                  onCite={onCite}
                  onRetry={() => void chat.retry(exchange.id)}
                  canRetry={!chat.isAsking && !isBlocked}
                  isPhone={isPhone}
                />
              </li>
            ))}
          </ol>
        </div>
      )}
    </section>
  )
}

/** One question and whatever became of it: a pending line, an answer, or the API's refusal. */
function Exchange({
  exchange,
  feedback,
  bidderLanguage,
  activeCitation,
  onCite,
  onRetry,
  canRetry,
  isPhone,
}: {
  readonly exchange: ChatExchange
  readonly feedback: RowFeedbackController
  readonly bidderLanguage: string
  readonly activeCitation: Citation | undefined
  readonly onCite: (citation: Citation) => void
  readonly onRetry: () => void
  readonly canRetry: boolean
  readonly isPhone: boolean
}) {
  const { outcome } = exchange
  return (
    <div className="flex flex-col gap-3">
      <div>
        <Eyebrow className="mb-1.5">You asked</Eyebrow>
        <p className="m-0 text-base leading-[1.5] font-medium text-text-primary whitespace-pre-line [overflow-wrap:anywhere]">
          {exchange.question}
        </p>
      </div>
      {outcome.phase === 'asking' && (
        <p className="m-0 [font:var(--type-body-sm)] text-text-muted">
          Asking… this takes a few seconds while the documents are searched.
        </p>
      )}
      {outcome.phase === 'answered' && (
        <>
          <Answer
            turn={outcome.turn}
            bidderLanguage={bidderLanguage}
            activeCitation={activeCitation}
            onCite={onCite}
            isPhone={isPhone}
          />
          <FeedbackControls
            target={answerTarget(exchange.id)}
            feedback={feedback}
            question="Was this answer right?"
            keptNote="Kept with this bid — the record holds your thumb and comment, not which answer they were about."
            placeholder="The deadline is 7 October, not 7 September — see page 3."
            isPhone={isPhone}
          />
        </>
      )}
      {outcome.phase === 'failed' && (
        <div className="flex flex-col gap-2">
          <p className="m-0 [font:var(--type-body-sm)] text-status-danger-text">
            Not answered: {outcome.message}
          </p>
          <Button
            variant="secondary"
            size={isPhone ? 'md' : 'sm'}
            className="self-start"
            disabled={!canRetry}
            onClick={onRetry}
          >
            Ask again
          </Button>
        </div>
      )}
    </div>
  )
}

/**
 * The answer, then either its sources or the notice that it has none. `lang` is the
 * bidder's language because that is what the server answers in (the chrome stays English,
 * a settled decision), so a screen reader switches voice for the paragraph and back.
 */
function Answer({
  turn,
  bidderLanguage,
  activeCitation,
  onCite,
  isPhone,
}: {
  readonly turn: ChatTurn
  readonly bidderLanguage: string
  readonly activeCitation: Citation | undefined
  readonly onCite: (citation: Citation) => void
  readonly isPhone: boolean
}) {
  const isCited = turn.citations.length > 0
  return (
    <div className="flex flex-col gap-2.5">
      <div>
        <Eyebrow className="mb-1.5">Answer</Eyebrow>
        <p
          lang={bidderLanguage}
          className="m-0 text-base leading-[1.5] text-text-primary whitespace-pre-line [overflow-wrap:anywhere]"
        >
          {turn.content}
        </p>
      </div>
      {isCited ? (
        <div>
          <Eyebrow className="mb-1.5">Sources</Eyebrow>
          <EvidenceList
            evidence={turn.citations}
            activeCitation={activeCitation}
            onCite={onCite}
            isPhone={isPhone}
          />
        </div>
      ) : (
        <Notice title="No source behind this answer">
          Nothing in the tender, your documents or the matrix was found to cite, so none of it
          has been checked against a page. Treat it as a lead, not as evidence.
        </Notice>
      )}
    </div>
  )
}
