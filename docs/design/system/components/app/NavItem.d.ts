/** Sidebar row: 32px blue icon tile + 15px label; active = white card. */
export interface NavItemProps {
  icon: React.ReactNode;
  label: string;
  active?: boolean;
  tone?: 'soft' | 'solid';
  trailing?: React.ReactNode;
  onClick?: () => void;
}
export function NavItem(props: NavItemProps): JSX.Element;
