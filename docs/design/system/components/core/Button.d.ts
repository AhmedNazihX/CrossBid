/** Primary action control. Sentence-case verb+object label.
 * @startingPoint section="Core" subtitle="Primary, secondary, ghost, inverse, danger" viewport="700x200" */
export interface ButtonProps {
  variant?: 'primary' | 'secondary' | 'ghost' | 'inverse' | 'danger';
  size?: 'sm' | 'md' | 'lg';
  icon?: React.ReactNode;
  iconRight?: React.ReactNode;
  fullWidth?: boolean;
  disabled?: boolean;
  onClick?: () => void;
  children?: React.ReactNode;
}
export function Button(props: ButtonProps): JSX.Element;
