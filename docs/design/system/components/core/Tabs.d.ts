/** Segmented control (blue fill on active) or underline tabs. */
export interface TabsProps {
  items: { label: string; value: string; count?: number }[];
  value?: string;
  onChange?: (value: string) => void;
  variant?: 'segmented' | 'underline';
}
export function Tabs(props: TabsProps): JSX.Element;
