/** Go / No-go / Conditional / Insufficient evidence chip using verdict tokens. */
export interface VerdictChipProps {
  verdict: 'go' | 'nogo' | 'conditional' | 'insufficient';
  size?: 'sm' | 'md' | 'lg';
  confirmed?: boolean;
}
export function VerdictChip(props: VerdictChipProps): JSX.Element;
