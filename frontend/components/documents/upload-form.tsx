'use client'

import { useId, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Notice } from '@/components/ui/notice'
import { Select } from '@/components/ui/select'
import {
  DOCUMENT_KINDS,
  isDocumentKind,
  MAX_UPLOAD_MEGABYTES,
  validateUploadFile,
  type DocumentKind,
} from '@/lib/documents'
import { DOCUMENT_KIND_LABELS } from './document-labels'

const DEFAULT_KIND: DocumentKind = 'company_evidence'

export interface UploadFormProps {
  /** Resolves when the API accepted the file; rejects with the error to show. */
  readonly onUpload: (file: File, kind: DocumentKind) => Promise<void>
}

/**
 * File + kind + submit (story S4.2.2) on the design system's `Input`, `Select` and `Button`
 * (`components/forms/*.jsx`, ADR-0014). The browser's own file input and a native `<select>`
 * sit inside the styled boxes, so keyboard and screen-reader behaviour stay complete.
 */
export function UploadForm({ onUpload }: UploadFormProps) {
  const fileId = useId()
  const kindId = useId()
  const [kind, setKind] = useState<DocumentKind>(DEFAULT_KIND)
  const [error, setError] = useState<string | undefined>(undefined)
  const [isUploading, setIsUploading] = useState(false)

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const file = new FormData(form).get('file')
    const chosenFile = file instanceof File ? file : undefined

    const problem = validateUploadFile(chosenFile)
    if (problem !== undefined || chosenFile === undefined) {
      setError(problem ?? 'Choose a PDF to upload.')
      return
    }

    setError(undefined)
    setIsUploading(true)
    try {
      await onUpload(chosenFile, kind)
      form.reset()
      setKind(DEFAULT_KIND)
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
          label="PDF file"
          name="file"
          type="file"
          accept="application/pdf,.pdf"
          required
          disabled={isUploading}
          hint={`One PDF, up to ${MAX_UPLOAD_MEGABYTES} MB.`}
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
