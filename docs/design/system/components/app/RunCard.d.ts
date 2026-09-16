/** Agent run summary row: title, one-line summary, status badge + meta.
 * @startingPoint section="App" subtitle="Agent run summary card" viewport="700x180" */
export interface RunCardProps {
  title: string;
  summary?: string;
  status?: 'success' | 'warning' | 'danger' | 'info' | 'neutral';
  statusLabel?: string;
  meta?: { icon?: React.ReactNode; label: string }[];
  actionLabel?: string;
  onAction?: () => void;
}
export function RunCard(props: RunCardProps): JSX.Element;
