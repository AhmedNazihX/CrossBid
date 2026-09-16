/** Square icon-only button; always pass an accessible label. */
export interface IconButtonProps {
  variant?: 'secondary' | 'ghost';
  size?: 'sm' | 'md' | 'lg';
  label: string;
  active?: boolean;
  disabled?: boolean;
  onClick?: () => void;
  children: React.ReactNode;
}
export function IconButton(props: IconButtonProps): JSX.Element;
