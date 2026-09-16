/** White bordered surface, 12px radius, optional header row.
 * @startingPoint section="Core" subtitle="Bordered white card with header" viewport="700x220" */
export interface CardProps {
  title?: React.ReactNode;
  icon?: React.ReactNode;
  actions?: React.ReactNode;
  padding?: number | string;
  hoverable?: boolean;
  onClick?: () => void;
  children?: React.ReactNode;
}
export function Card(props: CardProps): JSX.Element;
