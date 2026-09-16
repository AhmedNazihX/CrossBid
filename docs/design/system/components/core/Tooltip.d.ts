/** Dark hover tooltip. */
export interface TooltipProps {
  content: React.ReactNode;
  side?: 'top' | 'bottom';
  children: React.ReactNode;
}
export function Tooltip(props: TooltipProps): JSX.Element;
