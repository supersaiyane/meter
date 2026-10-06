import { useId, type ReactNode } from 'react';

/**
 * A chart on the screen that owns its numbers, TASK-P8-013: a titled panel and one sentence on
 * what is drawn and from what, then the chart, which carries its own table of numbers.
 */
export interface ChartPanelProps {
  readonly id: string;
  readonly title: string;
  readonly caption: string;
  readonly children: ReactNode;
}

export function ChartPanel({ id, title, caption, children }: ChartPanelProps) {
  const heading = useId();
  return (
    <section data-testid={`chart-${id}`} className="meter-panel" aria-labelledby={heading}>
      <h2 id={heading}>{title}</h2>
      <p data-testid="chart-caption">{caption}</p>
      {children}
    </section>
  );
}
