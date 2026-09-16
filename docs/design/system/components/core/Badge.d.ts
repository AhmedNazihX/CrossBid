/** Status chip with tinted background and dot or icon. */
export interface BadgeProps {
  tone?: 'success' | 'warning' | 'danger' | 'info' | 'neutral' | 'brand';
  dot?: boolean;
  icon?: React.ReactNode;
  size?: 'sm' | 'md';
  pill?: boolean;
  children: React.ReactNode;
}
export function Badge(props: BadgeProps): JSX.Element;
