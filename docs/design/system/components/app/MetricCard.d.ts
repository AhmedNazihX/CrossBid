/** KPI card: muted label, 32px value, colored delta + period. */
export interface MetricCardProps {
  label: string;
  value: React.ReactNode;
  delta?: string;
  deltaTone?: 'success' | 'danger' | 'neutral';
  period?: string;
}
export function MetricCard(props: MetricCardProps): JSX.Element;
