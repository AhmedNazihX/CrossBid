import { cn } from 'cn'

/**
 * VerdictChip — `components/app/VerdictChip.jsx`: the four verdict words of the fixed
 * vocabulary (ADR-0013) on their verdict tokens, 8 px dot, 8 px radius, semibold. The
 * `Decision` enum values of the API map onto it one to one.
 */
export type VerdictValue = 'go' | 'no_go' | 'conditional' | 'insufficient_evidence'

const VERDICTS: Readonly<Record<VerdictValue, { label: string; chip: string; dot: string }>> = {
  go: { label: 'Go', chip: 'bg-verdict-go-bg text-verdict-go-text', dot: 'bg-verdict-go' },
  no_go: {
    label: 'No-go',
    chip: 'bg-verdict-nogo-bg text-verdict-nogo-text',
    dot: 'bg-verdict-nogo',
  },
  conditional: {
    label: 'Conditional',
    chip: 'bg-verdict-conditional-bg text-verdict-conditional-text',
    dot: 'bg-verdict-conditional',
  },
  insufficient_evidence: {
    label: 'Insufficient evidence',
    chip: 'bg-verdict-insufficient-bg text-verdict-insufficient-text',
    dot: 'bg-verdict-insufficient',
  },
}

const SIZE_CLASSES = {
  sm: 'px-2 py-1 text-sm',
  md: 'px-3 py-[7px] text-base',
  lg: 'px-3.5 py-2.5 text-[16px]',
} as const

export interface VerdictChipProps {
  readonly verdict: VerdictValue
  readonly size?: keyof typeof SIZE_CLASSES
  readonly confirmed?: boolean
  readonly className?: string
}

export function VerdictChip({
  verdict,
  size = 'md',
  confirmed = false,
  className,
}: VerdictChipProps) {
  const entry = VERDICTS[verdict]
  return (
    <span
      className={cn(
        'inline-flex items-center gap-2 rounded-md font-semibold leading-none whitespace-nowrap',
        SIZE_CLASSES[size],
        entry.chip,
        className
      )}
    >
      <span aria-hidden="true" className={cn('size-2 rounded-full', entry.dot)} />
      {entry.label}
      {confirmed && <span className="font-normal opacity-80">· confirmed</span>}
    </span>
  )
}
