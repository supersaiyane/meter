import type { ApiQueryFinding } from '../api/types';

/** What a finding with no dashboard is: an alert rule or a query somebody ran by hand. */
const NO_DASHBOARD = 'Not on a dashboard';

/** Each dashboard's queries, summed: what the dashboard costs to keep on screen each month. */
export function byDashboard(
  findings: readonly ApiQueryFinding[],
): readonly { readonly label: string; readonly value: number }[] {
  const totals = new Map<string, number>();
  for (const one of findings) {
    const name = one.dashboard_title ?? NO_DASHBOARD;
    totals.set(name, (totals.get(name) ?? 0) + Number(one.monthly_cost));
  }
  return [...totals]
    .map(([label, value]) => ({ label, value }))
    .sort((left, right) => right.value - left.value);
}
