/** Neutral bordered label for metadata, filters, and citations (mono). */
export interface TagProps {
  children: React.ReactNode;
  onRemove?: () => void;
  mono?: boolean;
}
export function Tag(props: TagProps): JSX.Element;
