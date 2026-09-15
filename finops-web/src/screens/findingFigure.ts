import type { ApiQueryFindingDetail } from '../api/types';
import type { FigureValue } from '../components/provenance';

/**
 * A finding's cost as a figure, with its provenance and its accuracy.
 *
 * Separate from the screen for the same reason `platformRollUp` is: the mapping
 * has two branches that must both be provable, and a pure function is provable
 * without rendering anything.
 *
 * The accuracy is passed through only when FEAT-018 published one. It is never
 * invented, never written as prose beside the figure, and never attached to a
 * measured number: `Figure` renders "accuracy not yet published" from its
 * absence, so an absent accuracy is already the honest rendering.
 */
export function amountFigure(detail: ApiQueryFindingDetail): FigureValue {
  const amount = Number(detail.monthly_cost);
  if (detail.provenance === 'measured') {
    return { kind: 'measured', amount };
  }
  return {
    kind: 'modelled',
    amount,
    ...(detail.accuracy_percent !== null
      ? { accuracy: `+/- ${String(detail.accuracy_percent)}%` }
      : {}),
  };
}
