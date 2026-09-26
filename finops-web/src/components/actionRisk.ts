/**
 * The words for what applying a finding costs if it is wrong.
 *
 * In its own module rather than beside the panel for two reasons. The React Refresh rule
 * refuses a file that exports both a component and a value, which is the same reason
 * `querySeverity.ts` exists. And the entity detail page shows the same label against the
 * same findings, so a second copy of this wording would be a second answer to how dangerous
 * a change is.
 *
 * **Wording only.** The rule lives in `finops_query/actions.py` and arrives on the row as
 * three booleans, so nothing here can disagree with the server about which findings are
 * which. If this file decided anything it would be the second implementation of a domain
 * rule, which is how the two come to differ.
 */

/** How many rows per group on the home panel. Five reads well and is what fits. */
export const PER_GROUP = 5;

/**
 * The three booleans `riskLabel` reads, and nothing else.
 *
 * Narrower than `ApiRecommendation` on purpose. FEAT-055's commitment actions live in their own
 * payload, because a payer wide finding cannot sit in the per account findings table (ADR-0025),
 * and they still have to be labelled with the same words. A signature demanding a whole
 * recommendation forced the first draft of that screen to cast a three field object through
 * `never`, which is a lie the compiler was talked out of noticing.
 */
export interface RiskVerdict {
  readonly reversible: boolean;
  readonly disturbs_running_work: boolean;
  readonly is_no_regret: boolean;
}

/**
 * The risk of one row, leading with the part that cannot be undone.
 *
 * Permanent comes first on purpose. Five of the eight waste classes that disturb nothing
 * cannot be reversed, including the two a reader is most likely to apply without thinking,
 * so a label that led with the absence of disruption would be reassuring about exactly the
 * wrong findings.
 */
export function riskLabel(row: RiskVerdict): string {
  if (row.is_no_regret) return 'no regret';
  if (!row.reversible && row.disturbs_running_work) return 'permanent, interrupts the workload';
  if (!row.reversible) return 'permanent';
  return 'interrupts the workload';
}
