/** Bottom-right notification card with status dot. */
export interface ToastProps {
  tone?: 'success' | 'warning' | 'danger' | 'info';
  title: React.ReactNode;
  description?: React.ReactNode;
  action?: React.ReactNode;
  onDismiss?: () => void;
}
export function Toast(props: ToastProps): JSX.Element;
