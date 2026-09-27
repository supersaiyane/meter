import type { ApiBudget } from '../api/types';

/**
 * A budget's spend against its limit, with the calendar drawn on top of it. FEAT-060.
 *
 * **Its own component because two screens draw it and they must not disagree.** The home tile
 * and the budgets screen show the same budget, and a fill computed one way in one place and
 * another way in the other is two pictures of one fact. The rule that matters is the clamp: a
 * budget at a hundred and seven percent draws a full bar and says OVER beside it, because a bar
 * running past its own track is a drawing that cannot be compared with the one next to it.
 *
 * **The tick is the point.** Ninety five percent spent is healthy on the twenty eighth and
 * alarming on the fourth, so the fill alone carries no finding. The tick is where the period has
 * got to, and the gap between the two is what a reader is actually looking for.
 */

function percentOf(fraction: string): string {
  return `${(Number(fraction) * 100).toFixed(0)}%`;
}

export function BudgetBar({ budget }: { readonly budget: ApiBudget }) {
  // Clamped, so the fill never runs past its own track. The status says OVER; the bar says full.
  const used = budget.used === null ? 0 : Math.min(Number(budget.used), 1);
  const elapsed = Number(budget.elapsed);
  return (
    <>
      <div
        data-testid="budget-bar"
        role="img"
        aria-label={
          `${percentOf(budget.used ?? '0')} of the budget spent, ` +
          `${percentOf(budget.elapsed)} of the period elapsed`
        }
      >
        <i style={{ width: `${String(used * 100)}%` }} data-over={budget.status === 'OVER'} />
        <b style={{ left: `${String(elapsed * 100)}%` }} />
      </div>
      <p data-testid="budget-pace">
        <span>{percentOf(budget.used ?? '0')} spent</span>
        <span>{percentOf(budget.elapsed)} of the period gone</span>
      </p>
    </>
  );
}
