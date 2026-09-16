/** Text input with optional label, leading icon, hint, and error. */
export interface InputProps {
  label?: string;
  hint?: string;
  error?: string;
  icon?: React.ReactNode;
  size?: 'sm' | 'md' | 'lg';
  placeholder?: string;
  value?: string;
  onChange?: (e: React.ChangeEvent<HTMLInputElement>) => void;
  disabled?: boolean;
}
export function Input(props: InputProps): JSX.Element;
