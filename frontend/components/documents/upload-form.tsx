'use client'

import { useId, useState } from 'react'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
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
 * File + kind + submit, in stock shadcn/ui inputs (story S4.2.2).
 *
 * The browser's own file input and a native `<select>` are used rather than styled
 * replacements because they are keyboard- and screen-reader-complete out of the box, and
 * the upload screen is exempt from the S4.0.1 design gate only while it stays stock.
 * Controls are 44 px tall at phone width (`h-11`) and shrink to the shell's 32 px on `sm:`.
 */
export function UploadForm({ onUpload }: UploadFormProps) {
  const fileId = useId()
  const kindId = useId()
  const errorId = useId()
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

  function handleKindChange(event: React.ChangeEvent<HTMLSelectElement>) {
    const next = event.target.value
    if (isDocumentKind(next)) {
      setKind(next)
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      aria-busy={isUploading}
      className="flex flex-col gap-4"
      noValidate
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-2">
          <Label htmlFor={fileId}>PDF file</Label>
          <Input
            id={fileId}
            name="file"
            type="file"
            accept="application/pdf,.pdf"
            required
            disabled={isUploading}
            aria-invalid={error !== undefined || undefined}
            aria-describedby={
              error === undefined ? `${fileId}-hint` : `${errorId} ${fileId}-hint`
            }
            className="h-11 py-2 file:h-7 sm:h-8 sm:py-1 sm:file:h-6"
          />
          <p id={`${fileId}-hint`} className="text-muted-foreground text-xs">
            One PDF, up to {MAX_UPLOAD_MEGABYTES} MB.
          </p>
        </div>

        <div className="flex flex-col gap-2">
          <Label htmlFor={kindId}>Document type</Label>
          <NativeSelect
            id={kindId}
            name="kind"
            value={kind}
            onChange={handleKindChange}
            disabled={isUploading}
            aria-describedby={`${kindId}-hint`}
            className="w-full [&_select]:h-11 sm:[&_select]:h-8"
          >
            {DOCUMENT_KINDS.map((option) => (
              <NativeSelectOption key={option} value={option}>
                {DOCUMENT_KIND_LABELS[option].label}
              </NativeSelectOption>
            ))}
          </NativeSelect>
          <p id={`${kindId}-hint`} className="text-muted-foreground text-xs">
            {DOCUMENT_KIND_LABELS[kind].hint}
          </p>
        </div>
      </div>

      {error !== undefined && (
        <Alert id={errorId} variant="destructive">
          <AlertTitle>The file was not uploaded</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <div>
        <Button
          type="submit"
          size="lg"
          disabled={isUploading}
          className="h-11 w-full sm:h-9 sm:w-auto"
        >
          {isUploading ? 'Uploading…' : 'Upload'}
        </Button>
      </div>
    </form>
  )
}
