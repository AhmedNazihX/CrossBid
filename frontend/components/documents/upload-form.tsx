'use client'

import { useId, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Notice } from '@/components/ui/notice'
import { Select } from '@/components/ui/select'
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
  /** Resolves when the API accepted the file; rejects with the error to show. */
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
 */
export function UploadForm({ onUpload, defaultKind = FALLBACK_KIND }: UploadFormProps) {
  const fileId = useId()
  const kindId = useId()
  const [kind, setKind] = useState<DocumentKind>(defaultKind)
  const [error, setError] = useState<string | undefined>(undefined)
  const [isUploading, setIsUploading] = useState(false)
  // The ESPD request is XML and every other kind is a PDF, so the picker's filter, its hint
  // and the refusals all follow the chosen type rather than assuming one shape.
  const shape = uploadShapeFor(kind)

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const file = new FormData(form).get('file')
    const chosenFile = file instanceof File ? file : undefined

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
      setError(cause instanceof Error ? cause.message : 'The upload failed. Try again.')
    } finally {
      setIsUploading(false)
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      aria-busy={isUploading}
      className="flex flex-col gap-4"
      noValidate
    >
      <div className="grid gap-4 shell:grid-cols-2">
        <Input
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

      {error !== undefined && (
        <Notice tone="danger" title="The file was not uploaded">
          {error}
        </Notice>
      )}

      <div>
        <Button type="submit" size="lg" disabled={isUploading} className="w-full shell:w-auto">
          {isUploading ? 'Uploading…' : 'Upload file'}
        </Button>
      </div>
    </form>
  )
}
