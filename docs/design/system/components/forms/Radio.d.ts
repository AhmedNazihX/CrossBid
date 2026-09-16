/** Radio group; 18px circles with thick blue ring when selected. */
export interface RadioProps {
  options: { label: string; value: string; description?: string }[];
  value?: string;
  onChange?: (value: string) => void;
  name?: string;
  direction?: 'column' | 'row';
}
export function Radio(props: RadioProps): JSX.Element;
