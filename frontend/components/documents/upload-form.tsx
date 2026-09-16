'use client'

import { useId, useRef, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Notice } from '@/components/ui/notice'
import { Select } from '@/components/ui/select'
import { describeApiError } from '@/lib/api-client'
import { retryAt, useRateLimit } from '@/lib/use-rate-limit'
import {
  DOCUMENT_KINDS,
  isDocumentKind,
  uploadShapeFor,
  validateUploadFile,
  type DocumentKind,
} from '@/lib/documents'
import { DOCUMENT_KIND_LABELS } from './document-labels'

/**
 * What the type select shows when the caller does not say. `/company` is where the
 * certificates live, so evidence is the right first guess there; a page that is about a
 * tender pack has to say so through `defaultKind`, because the start step never sees
 * evidence and a pack uploaded under this fallback would vanish from it (2026-09-15).
 */
const FALLBACK_KIND: DocumentKind = 'company_evidence'

export interface UploadFormProps {
  /**
   * Resolves when the API accepted the file; rejects with what the call threw. An `ApiError`
   * must arrive as itself, not wrapped: this form reads its status and `Retry-After` to tell
   * a full hour's allowance from a bad file (audit M12), and `describeApiError` turns either
   * into the sentence shown.
   */
  readonly onUpload: (file: File, kind: DocumentKind) => Promise<void>
  /**
   * The type the select starts on and returns to after each upload. A pack is twenty files
   * of the same kind, so the value the form snaps back to is the one the bidder types least.
   */
  readonly defaultKind?: DocumentKind
}

/**
 * File + kind + submit (story S4.2.2) on the design system's `Input`, `Select` and `Button`
 * (`components/forms/*.jsx`, ADR-0014). The browser's own file input and a native `<select>`
 * sit inside the styled boxes, so keyboard and screen-reader behaviour stay complete.
 *
 * **A 429 is a wait, not an error.** `document_upload_limit` is thirty an hour per company,
 * and a pack is twenty files, so a bidder can genuinely hit it. When they do, the button is
 * disabled until the second the API named and the notice says the clock time, the way the
 * ask panel does (`lib/use-rate-limit.ts`); until 2026-09-16 the API's sentence was shown
 * with the button still live, so the number in it was stale and the next press was refused.
 */
export function UploadForm({ onUpload, defaultKind = FALLBACK_KIND }: UploadFormProps) {
  const fileId = useId()
  const kindId = useId()
  const fileRef = useRef<HTMLInputElement>(null)
  const [kind, setKind] = useState<DocumentKind>(defaultKind)
  const [error, setError] = useState<string | undefined>(undefined)
  const [isUploading, setIsUploading] = useState(false)
  const rateLimit = useRateLimit()
  // The ESPD request is XML and every other kind is a PDF, so the picker's filter, its hint
  // and the refusals all follow the chosen type rather than assuming one shape.
  const shape = uploadShapeFor(kind)

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    // Read from the input itself rather than `new FormData(form)`: the two agree in every
    // browser, but jsdom's form-data algorithm never sees a `FileList` set on the element,
    // so the FormData route made the form untestable while looking perfectly fine live.
    const chosenFile = fileRef.current?.files?.[0]

    const problem = validateUploadFile(chosenFile, kind)
    if (problem !== undefined || chosenFile === undefined) {
      setError(problem ?? shape.missing)
      return
    }

    setError(undefined)
    setIsUploading(true)
    try {
      await onUpload(chosenFile, kind)
      form.reset()
      setKind(defaultKind)
    } catch (cause) {
      // A wait the hook can time is the hook's to say — clearing `error` here stops an older
      // refusal from resurfacing under the button the moment the wait lifts.
      setError(rateLimit.noteRefusal(cause) ? undefined : describeApiError(cause))
    } finally {
      setIsUploading(false)
    }
  }

  const message =
    rateLimit.blockedUntil === undefined
      ? error
      : `This company has used its hour's uploads. ${retryAt(rateLimit.blockedUntil)}`

  return (
    <form
      onSubmit={handleSubmit}
      aria-busy={isUploading}
      className="flex flex-col gap-4"
      noValidate
    >
      <div className="grid gap-4 shell:grid-cols-2">
        <Input
          ref={fileRef}
          id={fileId}
          label="File"
          name="file"
          type="file"
          accept={shape.accept}
          required
          disabled={isUploading}
          hint={shape.hint}
        />
        <Select
          id={kindId}
          label="Document type"
          name="kind"
          value={kind}
          onValueChange={(next) => {
            if (isDocumentKind(next)) {
              setKind(next)
            }
          }}
          disabled={isUploading}
          hint={DOCUMENT_KIND_LABELS[kind].hint}
          options={DOCUMENT_KINDS.map((option) => ({
            value: option,
            label: DOCUMENT_KIND_LABELS[option].label,
          }))}
        />
      </div>

      {message !== undefined && (
        <Notice tone="danger" title="The file was not uploaded">
          {message}
        </Notice>
      )}

      <div>
        <Button
          type="submit"
          size="lg"
          disabled={isUploading || rateLimit.isBlocked}
          className="w-full shell:w-auto"
        >
          {isUploading ? 'Uploading…' : 'Upload file'}
        </Button>
      </div>
    </form>
  )
}
