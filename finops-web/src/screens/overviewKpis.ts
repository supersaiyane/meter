import type {
  ApiBudget,
  ApiCommitments,
  ApiCostSlice,
  ApiExplore,
  ApiExploreWindow,
  ApiForecast,
  ApiReconciliation,
  ApiRecommendation,
} from '../api/types';
import { wasteClassName } from '../components/displayNames';
import { DAY_MS, exploreQuery } from './exploreSeries';
import { periodWords } from './reconciliationModel';

/**
 * The Overview's figures, FEAT-070 and P8 spec section 5.8, worked out here so each is tested
 * without a browser.
 *
 * Every figure is read from a route another screen already reads, and every one names its
 * formula and its baseline. A figure the data cannot support says why and carries no number,
 * because a KPI drawn as zero when it could not be measured is the failure this product exists
 * to prevent.
 */

export interface KpiFacts {
  readonly value: number | null;
  readonly previous: number | null;
  /** What the change is measured against, in words. */
  readonly period: string;
  readonly formula: string;
  readonly note?: string;
  /** Why the data cannot support this figure. When set there is no figure at all. */
  readonly unsupported?: string;
  readonly range?: { readonly low: number; readonly high: number };
}

/** Waste classes that change a running resource's size or type, rather than remove it. */
export const RIGHTSIZING: ReadonlySet<string> = new Set([
  'RIGHTSIZE_INSTANCE',
  'GRAVITON_CANDIDATE',
  'EBS_OVERPROVISIONED',
  'EBS_GP2_TO_GP3',
  'DYNAMODB_OVERPROVISIONED',
]);

/** The allocation grouping's name for spend carrying no value of the tag. */
const UNALLOCATED = 'unallocated';

/** A budget scope covering every account, the only one a pace for the whole estate can use. */
const ESTATE = 'ALL';

/** Cost Explorer's own default view, this month to date by service, and its List Cost twin. */
export const MONTH_BY_SERVICE = exploreQuery();
export const MONTH_LIST_COST = exploreQuery({ metric: 'list_cost' });

/** The tag the allocation screen reads by default, and the one the drawing allocates by. */
export const ALLOCATION_TAG = 'team';

function amount(text: string | null | undefined): number | null {
  if (text === null || text === undefined) {
    return null;
  }
  const value = Number(text);
  return Number.isFinite(value) ? value : null;
}

function sum(values: readonly (string | null)[]): number {
  return values.reduce((total, value) => total + (amount(value) ?? 0), 0);
}

/** A day as a person says it: 6 October. */
export function dayName(iso: string): string {
  return new Date(`${iso.slice(0, 10)}T00:00:00Z`).toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'long',
    timeZone: 'UTC',
  });
}

function between(window: ApiExploreWindow): string {
  return `${dayName(window.start)} to ${dayName(window.end)}`;
}

export function wholeDollars(value: number): string {
  const sign = value < 0 ? '-' : '';
  return `${sign}$${Math.abs(value).toLocaleString('en-GB', { maximumFractionDigits: 0 })}`;
}

export function percent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

/** Effective cost to date, against the same days of the month before. */
export function effectiveCost(view: ApiExplore | undefined): KpiFacts {
  const period = view === undefined ? 'the same days last month' : between(view.previous);
  const formula =
    view === undefined
      ? 'The sum of FOCUS Effective Cost this month to date'
      : `The sum of FOCUS Effective Cost from ${between(view.current)}: what was used, after ` +
        'discounts, with commitments spread over the days they cover';
  return {
    value: amount(view?.total_this_period),
    previous: view?.previous_collected === true ? amount(view.total_previous_period) : null,
    period,
    formula,
  };
}

/** The budget furthest ahead of its own calendar, which is the one somebody needs today. */
export function mostAtRisk(budgets: readonly ApiBudget[]): ApiBudget | null {
  const ranked = budgets
    .filter((one) => one.used !== null)
    .map((one) => ({ one, ahead: Number(one.used) - Number(one.elapsed) }))
    .sort((left, right) => right.ahead - left.ahead);
  return ranked[0]?.one ?? null;
}

/** The one budget covering every account, or null when there is none or more than one. */
export function estateBudget(budgets: readonly ApiBudget[]): ApiBudget | null {
  const estate = budgets.filter((one) => one.scope === ESTATE && amount(one.limit) !== null);
  return estate.length === 1 ? (estate[0] ?? null) : null;
}

/** Budget consumed against the share of its period gone, for the budget furthest ahead. */
export function budgetConsumed(budgets: readonly ApiBudget[]): KpiFacts {
  const worst = mostAtRisk(budgets);
  const formula =
    'Actual spend over the budget limit, against the share of the budget period that has passed';
  if (worst === null) {
    return { value: null, previous: null, period: 'its period', formula };
  }
  return {
    value: amount(worst.used),
    previous: null,
    period: 'its period',
    formula,
    note: `${percent(Number(worst.elapsed))} of the period gone, ${worst.name}`,
  };
}

/** Month end spend as the forecast's interval, or the forecast's own reason for withholding it. */
export function forecastToMonthEnd(
  forecast: ApiForecast | undefined,
  budget: ApiBudget | null,
): KpiFacts {
  const formula =
    forecast === undefined
      ? 'The spend forecast for the month end'
      : `The ${forecast.method} forecast's ${String(forecast.interval_percent)} percent ` +
        `interval, billed through ${dayName(forecast.billed_through)}`;
  const base = { value: null, previous: null, period: 'the month end', formula };
  if (forecast === undefined) {
    return base;
  }
  const figure = forecast.month_end.figure;
  if (figure === null) {
    return { ...base, unsupported: forecast.month_end.withheld ?? 'The forecast was withheld' };
  }
  const low = Number(figure.low);
  const high = Number(figure.high);
  const limit = budget === null ? null : amount(budget.limit);
  return {
    ...base,
    value: high,
    range: { low, high },
    ...(limit === null || limit === 0 || budget === null
      ? {}
      : {
          note: `${percent(low / limit)} to ${percent(high / limit)} of the ${budget.name} budget`,
        }),
  };
}

/**
 * Effective savings rate: one minus actual spend with discounts over the same use at the on
 * demand rate, the KPI library's definition. FOCUS List Cost is that on demand equivalent, and
 * a bill without it cannot support the figure at all.
 */
export function effectiveSavingsRate(
  effective: ApiExplore | undefined,
  list: ApiExplore | undefined,
): KpiFacts {
  const formula =
    'One minus FOCUS Effective Cost over FOCUS List Cost, month to date. List Cost is the on ' +
    'demand equivalent';
  const base = { value: null, previous: null, period: 'the on demand equivalent', formula };
  if (effective === undefined) {
    return base;
  }
  if (!effective.metrics_available.includes('list_cost')) {
    return {
      ...base,
      unsupported:
        'The bill carries no List Cost, so there is no on demand equivalent to measure it against',
    };
  }
  const spent = amount(effective.total_this_period);
  const onDemand = amount(list?.total_this_period);
  if (spent === null || onDemand === null || onDemand === 0) {
    return base;
  }
  return { ...base, value: 1 - spent / onDemand };
}

/** Spend covered by commitments over the spend they could cover, and how well they are used. */
export function commitmentCoverage(commitments: ApiCommitments | undefined): KpiFacts {
  const formula =
    commitments === undefined
      ? 'Spend covered by Savings Plans and Reserved Instances over the spend they could cover'
      : 'Spend covered by Savings Plans and Reserved Instances over the spend they could cover, ' +
        `${dayName(commitments.window_start)} to ${dayName(commitments.window_end)}`;
  const base = { value: null, previous: null, period: 'the coverage window', formula };
  if (commitments === undefined) {
    return base;
  }
  const eligible = sum(commitments.coverage.map((row) => row.eligible_spend));
  const covered = sum(commitments.coverage.map((row) => row.covered_spend));
  const committed = sum(commitments.commitments.map((one) => one.committed));
  const used = sum(commitments.commitments.map((one) => one.used));
  return {
    ...base,
    value: eligible === 0 ? null : covered / eligible,
    note:
      committed === 0 ? 'No commitment collected' : `Utilization ${percent(used / committed)}`,
  };
}

/** Effective cost carrying the tag over all effective cost, and what is left unallocated. */
export function costAllocated(
  slices: readonly ApiCostSlice[] | undefined,
  tag: string,
): KpiFacts {
  const formula = `Effective Cost carrying a ${tag} tag over all Effective Cost this period`;
  const base = { value: null, previous: null, period: 'this period', formula };
  if (slices === undefined) {
    return base;
  }
  const total = sum(slices.map((slice) => slice.effective_cost));
  const unallocated = sum(
    slices.filter((slice) => slice.name === UNALLOCATED).map((slice) => slice.effective_cost),
  );
  if (total === 0) {
    return base;
  }
  return {
    ...base,
    value: 1 - unallocated / total,
    note: `${wholeDollars(unallocated)} unallocated, by the ${tag} tag`,
  };
}

export interface Mover {
  readonly name: string;
  readonly change: number;
}

/** The services whose spend moved most against the same days last month, either way. */
export function topMovers(view: ApiExplore | undefined, count: number): readonly Mover[] {
  if (view === undefined) {
    return [];
  }
  return view.rows
    .filter((row) => row.previous_period !== null)
    .map((row) => ({
      name: row.first,
      change: Number(row.this_period) - Number(row.previous_period),
    }))
    .sort((left, right) => Math.abs(right.change) - Math.abs(left.change))
    .slice(0, count);
}

export interface Ranked {
  readonly label: string;
  readonly value: number;
}

/** Explore's rows ranked by this period's spend, the largest first. */
export function rankedRows(view: ApiExplore | undefined): readonly Ranked[] {
  return (view?.rows ?? [])
    .map((row) => ({ label: row.first, value: Number(row.this_period) }))
    .sort((left, right) => right.value - left.value);
}

/** The lifecycle of a recommendation nobody has yet accepted, rejected or finished. */
const OPEN = 'OPEN';

/**
 * The recommendations still waiting on somebody. One already accepted, rejected or done is not a
 * saving still to be had, the rule Top actions and the recommendations screen's total also keep.
 */
export function openRecommendations(
  recommendations: readonly ApiRecommendation[],
): readonly ApiRecommendation[] {
  return recommendations.filter((one) => one.lifecycle === OPEN);
}

/** An instance that needs a larger type: an added cost, never a saving. TASK-P9-008. */
export const UPSIZE = 'UPSIZE_INSTANCE';

/**
 * Open recommendations' estimated monthly savings by category, largest first. Modelled, and
 * never added to what was realized, which has its own screen. An Upsize is left out: it saves
 * nothing, and a category at nought in a list ranked by money reads as the least valuable action
 * rather than as a cost.
 */
export function savingsByCategory(
  recommendations: readonly ApiRecommendation[],
): readonly Ranked[] {
  const totals = new Map<string, number>();
  for (const one of openRecommendations(recommendations)) {
    if (one.waste_class === UPSIZE) {
      continue;
    }
    const name = wasteClassName(one.waste_class);
    totals.set(name, (totals.get(name) ?? 0) + Number(one.estimated_monthly_saving));
  }
  return [...totals]
    .map(([label, value]) => ({ label, value }))
    .sort((left, right) => right.value - left.value);
}

/** What the estate budget allows each day of its period, aligned to the chart's periods. */
export function dailyPace(
  budget: ApiBudget | null,
  periods: readonly string[],
): readonly (number | null)[] | undefined {
  const limit = budget === null ? null : amount(budget.limit);
  if (budget === null || limit === null) {
    return undefined;
  }
  // The period's end is exclusive, as the budgets route writes it: September is the first of
  // September to the first of October.
  const start = Date.parse(`${budget.period_start}T00:00:00Z`);
  const end = Date.parse(`${budget.period_end}T00:00:00Z`);
  const days = Math.round((end - start) / DAY_MS);
  return periods.map((day) => {
    const at = Date.parse(`${day}T00:00:00Z`);
    return at >= start && at < end ? limit / days : null;
  });
}

/**
 * How much of the last invoiced period Meter's rows match, FEAT-076: the invoiced amount before
 * tax on invoices whose state is Matched, over all invoiced before tax. Amounts are taken whole,
 * so a credit memo counts by its size rather than cancelling the invoice it corrects. A period
 * with nothing to compare, or a route that answered in words, has no figure and says why.
 */
export function invoiceMatch(
  data: ApiReconciliation | undefined,
  instead: string | null,
): KpiFacts {
  const formula =
    'Invoiced amount before tax on invoices Meter matches, over all invoiced before tax' +
    (data === undefined ? '' : `, billing period starting ${data.period}`);
  const base = { value: null, previous: null, period: 'the last invoiced period', formula };
  if (instead !== null) return { ...base, unsupported: instead };
  if (data === undefined) return base;
  if (data.state !== null) return { ...base, unsupported: periodWords(data) };
  const whole = (amount: string) => Math.abs(Number(amount));
  const matched = data.invoices.filter((one) => one.state === 'Matched');
  const total = data.invoices.reduce((sum, one) => sum + whole(one.invoice_before_tax), 0);
  const agreed = matched.reduce((sum, one) => sum + whole(one.invoice_before_tax), 0);
  return {
    ...base,
    value: total === 0 ? null : agreed / total,
    note: `${String(matched.length)} of ${String(data.invoices.length)} invoices matched`,
  };
}
