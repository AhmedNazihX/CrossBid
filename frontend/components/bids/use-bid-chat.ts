'use client'

import { useCallback, useEffect, useRef, useState } from 'react'

import { describeApiError } from '@/lib/api-client'
import { askAboutBid, type ChatCitation, type ChatTurn } from '@/lib/chat'
import { useRateLimit } from '@/lib/use-rate-limit'

/**
 * The questions asked about one bid in this browser session, and what became of each
 * (story S4.6.1).
 *
 * **This is the whole transcript the screen has.** The server keeps the thread on its
 * checkpointer so a follow-up reaches an agent that remembers the last question (ADR-0055),
 * but no route reads that thread back, so a reload starts the visible log empty while the
 * agent's memory does not. The controller does not pretend otherwise: nothing here is loaded
 * on mount, and the panel says so.
 *
 * **One question in flight, enforced by a ref.** A turn takes several seconds and costs a
 * model call, and the thread is last-write-wins on the server, so a second submit during the
 * first is both a bill and a corrupted conversation. A click handler reads the state of the
 * render it was created in, which is why the guard is a ref and not `isAsking` alone —
 * `useReviewSubmission` makes the same choice for the same reason.
 *
 * **A failure keeps the question.** The exchange stays in the log with the API's own
 * sentence under it and can be sent again in place, so a five-second call that fails does
 * not also cost the bidder what they typed. A retry replaces the failed exchange rather than
 * appending a twin: one question, one place in the log, whatever it took to answer it.
 *
 * **A 429 is a wait, not an error.** `useRateLimit` holds the second the API named so the
 * panel can disable the form until then and say the time; the treatment was written here
 * first (ADR-0058) and moved to `lib/use-rate-limit.ts` when the upload and start forms
 * needed the same one (audit M12). The failed exchange still shows the API's `detail`, which
 * carries the same number in prose, so a browser that could not read the header is never
 * told "something went wrong".
 *
 * Nothing aborts the call. The server has already spent the money and written the thread by
 * the time an abort could land; an unmounted panel drops the answer instead.
 */
export type ExchangeOutcome =
  | { readonly phase: 'asking' }
  | { readonly phase: 'answered'; readonly turn: ChatTurn }
  /** `message` is the API's own sentence, or the transport failure's. */
  | { readonly phase: 'failed'; readonly message: string }

export interface ChatExchange {
  readonly id: string
  readonly question: string
  readonly outcome: ExchangeOutcome
}

export interface BidChatController {
  /** Oldest first; the panel decides the reading order. */
  readonly exchanges: readonly ChatExchange[]
  /** True while a question is in flight — the form's "do not send another". */
  readonly isAsking: boolean
  /** Epoch milliseconds at which the API will take a question again; `undefined` when it will now. */
  readonly blockedUntil: number | undefined
  /** Sends a question. Blank input, a question already in flight, or an active limit is a no-op. */
  ask(question: string): Promise<void>
  /** Sends a failed exchange's question again, in place. A no-op for any other exchange. */
  retry(exchangeId: string): Promise<void>
}

export function useBidChat(bidId: string): BidChatController {
  const [exchanges, setExchanges] = useState<readonly ChatExchange[]>([])
  const { blockedUntil, noteRefusal } = useRateLimit()
  const isAskingRef = useRef(false)
  const isMountedRef = useRef(true)
  const nextIdRef = useRef(0)

  useEffect(() => {
    isMountedRef.current = true
    return () => {
      isMountedRef.current = false
    }
  }, [])

  const send = useCallback(
    async (id: string, question: string): Promise<void> => {
      if (isAskingRef.current) {
        return
      }
      isAskingRef.current = true
      setExchanges((all) => upsert(all, { id, question, outcome: { phase: 'asking' } }))
      try {
        const turn = await askAboutBid(bidId, question)
        if (isMountedRef.current) {
          setExchanges((all) =>
            upsert(all, { id, question, outcome: { phase: 'answered', turn } })
          )
        }
      } catch (cause) {
        if (!isMountedRef.current) {
          return
        }
        noteRefusal(cause)
        setExchanges((all) =>
          upsert(all, {
            id,
            question,
            outcome: { phase: 'failed', message: describeApiError(cause) },
          })
        )
      } finally {
        isAskingRef.current = false
      }
    },
    [bidId, noteRefusal]
  )

  const ask = useCallback(
    async (question: string): Promise<void> => {
      const trimmed = question.trim()
      if (trimmed === '' || (blockedUntil !== undefined && blockedUntil > Date.now())) {
        return
      }
      nextIdRef.current += 1
      await send(String(nextIdRef.current), trimmed)
    },
    [blockedUntil, send]
  )

  const retry = useCallback(
    async (exchangeId: string): Promise<void> => {
      const exchange = exchanges.find((e) => e.id === exchangeId)
      if (exchange === undefined || exchange.outcome.phase !== 'failed') {
        return
      }
      if (blockedUntil !== undefined && blockedUntil > Date.now()) {
        return
      }
      await send(exchange.id, exchange.question)
    },
    [blockedUntil, exchanges, send]
  )

  return {
    exchanges,
    isAsking: exchanges.some((e) => e.outcome.phase === 'asking'),
    blockedUntil,
    ask,
    retry,
  }
}

/** Every citation the answers so far have pointed at, for the source panel's document list. */
export function citationsOf(exchanges: readonly ChatExchange[]): readonly ChatCitation[] {
  return exchanges.flatMap((e) =>
    e.outcome.phase === 'answered' ? e.outcome.turn.citations : []
  )
}

/** A copy with the exchange replaced where its id already is, appended where it is not. */
function upsert(all: readonly ChatExchange[], exchange: ChatExchange): readonly ChatExchange[] {
  const index = all.findIndex((e) => e.id === exchange.id)
  if (index === -1) {
    return [...all, exchange]
  }
  return [...all.slice(0, index), exchange, ...all.slice(index + 1)]
}
