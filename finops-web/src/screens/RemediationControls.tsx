import { useRemediate, useUndoRemediation } from '../api/queries';
import type { ApiQueryFindingDetail } from '../api/types';

/**
 * The two controls that change a panel, and the rules about when they exist.
 *
 * **Absent, not disabled.** A control that looks available and does nothing is
 * worse than one that is not there, which is the rule TASK-P2-025 states for
 * revoke and which holds here for the same reason: a reader who clicks a
 * disabled control learns nothing about why, and a reader who never sees one
 * asks the right question instead.
 *
 * So Undo exists only when there is a change still applied, which the API says
 * with `applied_change_id`, and Remediate exists only when there is not. They
 * are never both present, because the second one would be the first one's undo
 * under a different name.
 *
 * **The result is shown whatever it is.** A remediation can refuse, and can
 * revert itself when the write did not take, and both are normal answers that
 * carry a reason. Reporting only success would leave a reader believing the
 * estate changed when it did not, which is the failure this whole product is
 * built against.
 */
export interface RemediationControlsProps {
  readonly detail: ApiQueryFindingDetail;
}

export function RemediationControls({ detail }: RemediationControlsProps) {
  const remediate = useRemediate(detail.finding_id);
  const undo = useUndoRemediation(detail.finding_id);
  const active = detail.applied_change_id === null ? remediate : undo;
  const outcome = active.data?.data;

  return (
    <section aria-label="Remediation" data-testid="remediation">
      {detail.applied_change_id === null ? (
        <button
          type="button"
          data-testid="remediate"
          disabled={remediate.isPending}
          onClick={() => {
            remediate.mutate();
          }}
        >
          Slow this panel to the policy floor
        </button>
      ) : (
        <button
          type="button"
          data-testid="undo"
          disabled={undo.isPending}
          onClick={() => {
            undo.mutate();
          }}
        >
          Undo the last change
        </button>
      )}

      {outcome === undefined ? null : (
        <p
          data-testid="remediation-outcome"
          data-applied={outcome.applied ? 'true' : 'false'}
          className={outcome.applied ? undefined : 'meter-failure'}
        >
          {outcome.applied
            ? 'Done. The panel now refreshes at the policy floor.'
            : // The reason, verbatim. The server knows why it refused and the
              // screen paraphrasing it would be a second, worse explanation.
              outcome.detail}
        </p>
      )}

      {active.isError ? (
        <p data-testid="remediation-outcome" data-applied="false" className="meter-failure">
          The request did not reach the server, so nothing changed.
        </p>
      ) : null}
    </section>
  );
}
