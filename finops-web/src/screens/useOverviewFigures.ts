import { useMemo } from 'react';

import {
  useBudgets,
  useCostAllocation,
  useCostExplore,
  useCostForecast,
  useSavingsRate,
} from '../api/queries';
import type { ApiBudget, ApiCostSlice, ApiExplore, ApiForecast } from '../api/types';
import type { SurfaceState } from '../components/surfaceState';
import { useReportMeta } from '../shell/metaRegistry';
import {
  ALLOCATION_TAG,
  MONTH_BY_SERVICE,
  budgetConsumed,
  costAllocated,
  effectiveCost,
  effectiveSavingsRate,
  estateBudget,
  forecastToMonthEnd,
  mostAtRisk,
  type KpiFacts,
} from './overviewKpis';
import { surfaceStateFor } from './surfaceStateFor';

/**
 * The figures the FinOps and Executive dashboards share, FEAT-070, read once through the hooks
 * of the screens that own them. Each comes with the state of its read, so a tile shows a failure
 * as a failure and never as a figure that was simply not collected.
 */

/** The states in which nothing was read, so nothing can be said about what is absent. */
const UNREAD: ReadonlySet<SurfaceState['kind']> = new Set([
  'loading',
  'failed',
  'never-collected',
]);

export interface KpiRead {
  readonly facts: KpiFacts;
  readonly state: SurfaceState;
}

export interface OverviewFigures {
  readonly monthView: ApiExplore | undefined;
  readonly monthState: SurfaceState;
  readonly forecast: ApiForecast | undefined;
  readonly forecastState: SurfaceState;
  readonly worst: ApiBudget | null;
  readonly estate: ApiBudget | null;
  /** True once the budgets were read, so their absence is a fact rather than a failure. */
  readonly budgetsRead: boolean;
  readonly slices: readonly ApiCostSlice[] | undefined;
  readonly allocationState: SurfaceState;
  readonly cost: KpiRead;
  readonly forecastKpi: KpiRead;
  readonly budget: KpiRead;
  readonly savings: KpiRead;
  readonly allocated: KpiRead;
}

/** The worst budget's note, with how many others there are and how many carry no number. */
function budgetCount(total: number, unscored: number): string {
  if (total <= 1) {
    return 'the only budget collected';
  }
  const unnumbered = unscored === 0 ? '' : `, ${String(unscored)} with no number`;
  return `worst of ${String(total)} budgets${unnumbered}`;
}

export function useOverviewFigures(): OverviewFigures {
  // This month by service: Cost Explorer's own default view and its own query key.
  const month = useCostExplore(MONTH_BY_SERVICE, {
    title: 'Effective cost by service, month to date',
  });
  const monthView = month.data?.data;
  useReportMeta('overview-month', month.data?.meta);
  const monthState = surfaceStateFor(month, month.data?.meta, 1, 'none', 'cost_focus_daily');

  // FEAT-087. The rate the commitments screen opens on, read from the one route that computes
  // it and by the same twelve months, so the two share one answer: the newest billing month
  // against the one before.
  const savingsRate = useSavingsRate();
  useReportMeta('overview-savings-rate', savingsRate.data?.meta);
  const savingsState = surfaceStateFor(
    savingsRate,
    savingsRate.data?.meta,
    1,
    'none',
    'cost_focus_daily',
  );

  const forecastQuery = useCostForecast();
  const forecast = forecastQuery.data?.data;
  useReportMeta('overview-forecast', forecastQuery.data?.meta);
  const forecastState = surfaceStateFor(
    forecastQuery,
    forecastQuery.data?.meta,
    1,
    'none',
    'cost_focus_daily',
  );

  const budgets = useBudgets();
  const budgetEnvelope = budgets.data?.data;
  useReportMeta('overview-budgets', budgetEnvelope?.meta);
  const budgetRows = useMemo(() => budgetEnvelope?.data.budgets ?? [], [budgetEnvelope]);
  const budgetState = surfaceStateFor(
    budgets,
    budgetEnvelope?.meta,
    budgetRows.length,
    'none',
    'budgets',
  );
  const estate = estateBudget(budgetRows);
  const consumed = budgetConsumed(budgetRows);
  const count = budgetCount(budgetRows.length, budgetEnvelope?.data.unsupported ?? 0);

  const allocation = useCostAllocation(ALLOCATION_TAG);
  const allocationEnvelope = allocation.data?.data;
  useReportMeta('overview-allocation', allocationEnvelope?.meta);
  const slices = allocationEnvelope?.data;
  const allocationState = surfaceStateFor(
    allocation,
    allocationEnvelope?.meta,
    slices?.length ?? 0,
    'none',
    'cost_focus_daily',
  );

  return {
    monthView,
    monthState,
    forecast,
    forecastState,
    worst: mostAtRisk(budgetRows),
    estate,
    budgetsRead: !UNREAD.has(budgetState.kind),
    slices,
    allocationState,
    cost: { facts: effectiveCost(monthView), state: monthState },
    forecastKpi: { facts: forecastToMonthEnd(forecast, estate), state: forecastState },
    budget: {
      facts: {
        ...consumed,
        note: consumed.note === undefined ? count : `${consumed.note}, ${count}`,
      },
      state: budgetState,
    },
    savings: {
      facts: effectiveSavingsRate(savingsRate.data?.data),
      state: savingsState,
    },
    allocated: { facts: costAllocated(slices, ALLOCATION_TAG), state: allocationState },
  };
}
