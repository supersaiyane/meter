import type { ApiEstimateAccuracy, ApiEstimateComparison, ApiPlanEstimate } from '../api/types';
import { dayName } from './commitmentFormat';

/**
 * How the Estimates screen speaks of a plan, a change and the bill, TASK-P16-008. Kept apart from
 * the components so each panel file exports components only.
 */

/**
 * Within this many percent of the bill, at list, an estimate is right: the comparison's own rule,
 * `WITHIN_PERCENT` in `finops_query/estimate_accuracy.py`, which the accuracy route also sends.
 */
export const WITHIN_PERCENT = '10';

/** `acme/infra#7`, and its folder where it has one: `acme/infra#7, storage`. */
export function pullRequestName(plan: ApiPlanEstimate): string {
  const named = `${plan.repository}#${String(plan.pull_request)}`;
  return plan.folder === '' ? named : `${named}, ${plan.folder}`;
}

/** The unpriced count first, as the comment says it: `1 of 3 resources is not priced`. */
export function unpricedSentence(unpriced: number, total: number): string {
  if (total === 0) {
    return 'No resource changes';
  }
  if (unpriced === 0) {
    return total === 1
      ? 'The one resource is priced'
      : `All ${String(total)} resources are priced`;
  }
  const resources = total === 1 ? 'resource' : 'resources';
  const verb = unpriced === 1 ? 'is' : 'are';
  return `${String(unpriced)} of ${String(total)} ${resources} ${verb} not priced`;
}

/** Where a plan is: priced, waiting for the worker, or refused with why. */
export function planState(plan: ApiPlanEstimate): string {
  if (plan.status === 'REFUSED') {
    return `Refused: ${plan.reason ?? 'no reason was recorded'}`;
  }
  return plan.status === 'PRICED' ? 'Priced' : 'Waiting to be priced';
}

/** What happened to the plan's comment on its pull request, FEAT-096. */
export function commentState(plan: ApiPlanEstimate): string {
  switch (plan.comment_status) {
    case 'WRITTEN':
      return 'On the pull request';
    case 'SUPERSEDED':
      return `Not written: ${plan.comment_reason ?? 'a newer commit was planned'}`;
    case 'FAILED':
      return `Failed: ${plan.comment_reason ?? 'the code host refused it'}`;
    case null:
      return plan.status === 'PRICED' ? 'Waiting to be written' : 'None, as nothing was priced';
  }
}

const ACTION_NAMES: Readonly<Record<string, string>> = {
  create: 'Create',
  update: 'Change',
  delete: 'Destroy',
};

/** Terraform's actions as a reader says them; a delete and a create together are a replacement. */
export function actionsName(actions: readonly string[]): string {
  if (actions.includes('delete') && actions.includes('create')) {
    return 'Replace';
  }
  return actions.map((action) => ACTION_NAMES[action] ?? action).join(' and ');
}

/** A percentage the API sends with its column's places, `-27.2727`, without its sign. */
export function percentText(value: string): string {
  return `${Math.abs(Number(value)).toFixed(1).replace(/\.0$/, '')} percent`;
}

/** The last day of a window whose end the API sends exclusive. */
function lastDayOf(end: string): string {
  const day = new Date(`${end}T00:00:00Z`);
  day.setUTCDate(day.getUTCDate() - 1);
  return day.toISOString().slice(0, 10);
}

/** What the bill said of one created resource's estimate, FEAT-097. */
export function verdictSentence(
  comparison: ApiEstimateComparison,
  withinPercent: string,
): string {
  const variance = comparison.variance_percent;
  switch (comparison.verdict) {
    case 'PENDING':
      return comparison.window_end === null
        ? 'Seen, waiting for its thirty billed days'
        : `Waiting for the bill to reach ${dayName(lastDayOf(comparison.window_end))}`;
    case 'WITHIN':
      return `Within ${percentText(withinPercent)} of the bill`;
    case 'ABOVE':
      return `The bill came in ${variance === null ? '' : `${percentText(variance)} `}above`;
    case 'BELOW':
      return `The bill came in ${variance === null ? '' : `${percentText(variance)} `}below`;
    case 'NOT_COMPARED':
      return `Not compared: ${comparison.reason ?? 'no reason was recorded'}`;
  }
}

/** The headline: how many estimates came close, from the judged alone. */
export function accuracySentence(accuracy: ApiEstimateAccuracy): string {
  const all = accuracy.types.find((row) => row.resource_type === 'all');
  if (all === undefined || all.compared === 0 || all.median_error_percent === null) {
    return 'No estimate has been set against the bill yet: a resource a merged plan created needs thirty billed days first.';
  }
  return `${String(all.within)} of ${String(all.compared)} estimates came within ${percentText(accuracy.within_percent)} of the bill. The median error was ${percentText(all.median_error_percent)}.`;
}
