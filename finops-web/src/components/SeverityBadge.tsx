/**
 * Severity as a sequential ramp of one hue, with a label and a shape.
 *
 * Not a traffic light. Rank has to be readable without hue discrimination, so
 * the number of filled marks carries it as well as the fill does, and the text
 * label carries it a third time.
 */
export type Severity = 1 | 2 | 3 | 4 | 5;

const LABEL: Readonly<Record<Severity, string>> = {
  1: 'informational',
  2: 'low',
  3: 'medium',
  4: 'high',
  5: 'critical',
};

export interface SeverityBadgeProps {
  readonly level: Severity;
}

export function SeverityBadge({ level }: SeverityBadgeProps) {
  return (
    <span data-testid="severity" data-level={level}>
      <span aria-hidden="true">{'■'.repeat(level)}</span> {LABEL[level]}
    </span>
  );
}
