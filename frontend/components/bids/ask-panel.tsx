'use client'

import { useId, useState, type FormEvent, type KeyboardEvent } from 'react'
import { cn } from 'cn'

import type { Citation } from '@/components/matrix/citation'
import { EvidenceList } from '@/components/matrix/evidence-list'
import { FeedbackControls } from '@/components/matrix/row-feedback'
import { answerTarget, type RowFeedbackController } from '@/components/matrix/use-row-feedback'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Eyebrow } from '@/components/ui/eyebrow'
import { Icon } from '@/components/ui/icons'
import { Notice } from '@/components/ui/notice'
import { MAX_QUESTION_CHARS, type ChatTurn } from '@/lib/chat'
import { formatTime } from '@/lib/format'
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
 * inside one bordered, `--shadow-xs` box — and it is reproduced at the card's body scale,
 * because the artboard draws it at the dashboard's hero width and 17 px type does not fit a
 * 400 px column. The log of turns under it has no artboard: the canvas of ADR-0014 predates
 * the route. So, like `row-feedback.tsx`, it is assembled from primitives the artboards
 * already fixed — `Card`, `Eyebrow`, the matrix's own `EvidenceList` and `Notice`,
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
export function AskPanel({
  chat,
  feedback,
  bidderLanguage,
  activeCitation,
  onCite,
  variant = 'banner',
}: AskPanelProps) {
  const [draft, setDraft] = useState('')
  const fieldId = useId()
  const hintId = `${fieldId}-hint`
  const isPhone = variant === 'phone'
  const isBanner = variant === 'banner'
  const size = isPhone ? 'md' : 'sm'
  const isBlocked = chat.blockedUntil !== undefined
  const canSend = draft.trim() !== '' && !chat.isAsking && !isBlocked
  const newestFirst = [...chat.exchanges].reverse()

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

  const hint =
    chat.blockedUntil !== undefined
      ? `This company has used its hour's questions. Ask again at ${formatTime(new Date(chat.blockedUntil))}.`
      : 'Enter sends, Shift+Enter starts a new line. Answered from this tender, your documents and the matrix, in your language, with the page it came from.'

  return (
    <Card title="Ask the tender" icon={<Icon name="search" size={20} />} padding={20}>
      <form
        onSubmit={handleSubmit}
        className={cn(
          'rounded-[14px] border border-border-default bg-surface-card px-4 pt-3.5 pb-3 shadow-xs transition-shadow [transition-duration:var(--duration-fast)]',
          'focus-within:border-border-focus focus-within:shadow-[var(--shadow-focus)] focus-within:focus-ring'
        )}
      >
        <label htmlFor={fieldId} className="sr-only">
          Your question about this tender
        </label>
        <div className="flex items-start gap-3">
          <Icon name="search" size={20} className="mt-1.5 shrink-0 text-text-muted" />
          <textarea
            id={fieldId}
            rows={2}
            value={draft}
            maxLength={MAX_QUESTION_CHARS}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={handleKeyDown}
            aria-describedby={hintId}
            placeholder="Ask about this tender…"
            className="w-full min-w-0 resize-none bg-transparent py-1.5 text-base leading-[1.5] text-text-primary outline-none placeholder:text-text-placeholder"
          />
        </div>
        <div className="mt-3.5 flex items-end justify-between gap-3">
          <p
            id={hintId}
            className={cn(
              'm-0 [font:var(--type-body-sm)]',
              isBlocked ? 'text-text-secondary' : 'text-text-muted'
            )}
          >
            {hint}
          </p>
          <Button
            type="submit"
            size={size}
            disabled={!canSend}
            iconRight={<Icon name="arrow" size={16} />}
          >
            {chat.isAsking ? 'Asking…' : 'Ask'}
          </Button>
        </div>
      </form>

      {newestFirst.length === 0 ? (
        <p className="m-0 mt-4 [font:var(--type-body-sm)] text-text-secondary">
          Every answer points at a page you can open. What is asked here is kept with the bid on
          the server, so a follow-up question is understood in context — but only the questions
          asked in this tab are listed below.
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
    </Card>
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
