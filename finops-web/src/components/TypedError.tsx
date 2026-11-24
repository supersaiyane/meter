import { CAUSE_LABEL, type Cause } from './provenance';

/**
 * A failure, rendered as a cause and a way to act. Never as a number.
 *
 * The remediation is shown rather than linked, because a person reading a
 * column of costs at the moment one of them is missing will not go looking. The
 * cause is written in full rather than abbreviated, so a screenshot of this
 * pasted into a ticket still says what happened.
 */
export interface TypedErrorProps {
  readonly cause: Exclude<Cause, 'NoData'>;
  readonly remediation: string;
  readonly actionLabel?: string;
  readonly onAction?: () => void;
}

export function TypedError({ cause, remediation, actionLabel, onAction }: TypedErrorProps) {
  return (
    <span
      className="meter-failure"
      // Announced with its typed cause, so a cell that fails while somebody is
      // reading the table is heard rather than only seen.
      role="status"
      data-cause={cause}
    >
      <strong>{CAUSE_LABEL[cause]}</strong> <span>{remediation}</span>
      {onAction && actionLabel ? (
        <button type="button" onClick={onAction}>
          {actionLabel}
        </button>
      ) : null}
    </span>
  );
}
