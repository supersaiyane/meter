import { useBudgets } from '../api/queries';
import { BudgetBar } from '../components/BudgetBar';
import { FixtureBand } from '../components/FixtureBand';
import { StateBoundary } from '../components/StateBoundary';
import type { ApiBudget } from '../api/types';
import { useReportMeta } from '../shell/metaRegistry';
import { surfaceStateFor } from './surfaceStateFor';

/**
 * What was budgeted, what has been spent, and whether that is on course. FEAT-060.
 *
 * **The bar carries a pace marker, and that is the whole design.** A progress bar alone says
 * how much of a budget is gone, which on its own is not information: ninety percent spent is
 * healthy on the twenty eighth and alarming on the fourth. The tick is where the calendar has
 * got to, so the question a reader actually has, am I ahead or behind, is answered by whether
 * the bar has passed the tick. It is the same arithmetic the server does to produce the
 * status, drawn rather than described, so a reader can disagree with the light.
 *
 * **Four statuses and one of them is a refusal.** UNKNOWN is not amber and not grey noise: it
 * is a budget this product could not compute, either because no spend was collected or because
 * its scope is one we cannot reproduce. Those are listed separately with the reason, because a
 * screen showing two greens above ten blanks is saying something false about the estate.
 */

function money(amount: string, currency: string): string {
  return Number(amount).toLocaleString('en-GB', {
    style: 'currency',
    currency,
    currencyDisplay: 'narrowSymbol',
    maximumFractionDigits: 0,
  });
}

function Budget({ budget }: { readonly budget: ApiBudget }) {
  return (
    <article data-testid="budget" data-status={budget.status}>
      <header>
        <h3>{budget.name}</h3>
        <span data-testid="budget-status" data-status={budget.status}>
          {budget.status.replace('_', ' ').toLowerCase()}
        </span>
      </header>

      {budget.actual === null ? (
        // The refusal, said in words on the card itself rather than left as a blank bar. A
        // budget with no number is not a budget at zero, and the two look identical unless
        // one of them says so.
        <p data-testid="budget-unknown" data-state="never-collected">
          {budget.scope === 'UNSUPPORTED'
            ? 'No spend is compared against this. It is drawn around something Meter cannot ' +
              'reproduce, and a budget matched to the wrong spend is worse than one with no ' +
              'number.'
            : 'No cost has been collected for this period yet, which is not the same as ' +
              'nothing having been spent.'}
        </p>
      ) : (
        <>
          <p data-testid="budget-figure">
            <strong>{money(budget.actual, budget.currency)}</strong>
            <span> of {money(budget.limit, budget.currency)}</span>
          </p>
          <BudgetBar budget={budget} />
        </>
      )}
    </article>
  );
}

export function BudgetsScreen() {
  const query = useBudgets();
  const envelope = query.data?.data;
  useReportMeta('cost-budgets', envelope?.meta);

  const found = envelope?.data;
  const all = found?.budgets ?? [];
  const tracked = all.filter((one) => one.actual !== null);
  const untracked = all.filter((one) => one.actual === null);
  const state = surfaceStateFor(query, envelope?.meta, all.length, 'none', 'budgets');

  return (
    <section aria-label="Budgets">
      <FixtureBand source={query.data?.source} />
      <StateBoundary state={state}>
        <>
          <p data-testid="budgets-period">
            Period {found?.period ?? 'not resolved'}. Read from the provider, never entered
            here, so every limit below is the one the provider is already alerting on.
          </p>

          <div data-testid="budgets-tracked">
            {tracked.map((one) => (
              <Budget key={one.budget_id} budget={one} />
            ))}
          </div>

          {untracked.length > 0 ? (
            // Separated and counted, never mixed in with the ones that have a status. A list
            // of two greens above ten blanks reads as an estate that is mostly fine.
            <>
              <h3 data-testid="budgets-untracked-heading">
                {untracked.length === 1
                  ? 'One budget with no number'
                  : `${String(untracked.length)} budgets with no number`}
              </h3>
              <div data-testid="budgets-untracked">
                {untracked.map((one) => (
                  <Budget key={one.budget_id} budget={one} />
                ))}
              </div>
            </>
          ) : null}
        </>
      </StateBoundary>
    </section>
  );
}
