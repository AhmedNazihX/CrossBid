/** Bordered dropdown trigger (chevrons-up-down) with popover list; doubles as filter pill. */
export interface SelectProps {
  label?: string;
  options: { label: string; value: string }[];
  value?: string;
  placeholder?: string;
  onChange?: (value: string) => void;
  size?: 'sm' | 'md';
}
export function Select(props: SelectProps): JSX.Element;
