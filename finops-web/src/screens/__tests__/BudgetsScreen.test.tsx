import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { BudgetsScreen } from '../BudgetsScreen';
import { Harness } from './Harness';
import { clientReturning } from './fixtures';
import { costBudgetsFixture } from '../../api/fixtures/cost';
import type { ApiBudget, ApiBudgets, ApiEnvelope } from '../../api/types';
import { violationsIn } from '../../components/__tests__/axe';

/**
 * FEAT-060. The cases that carry this file are the pace marker and the refusal.
 *
 * The failure being guarded is a screen that shows a bar at ninety five percent and lets a
 * reader conclude the budget is nearly gone, when what matters is whether ninety five percent
 * spent is early or late. The second failure is the one every dashboard makes: a budget with no
 * number rendered as a budget at zero, which reads as an estate underspending.
 */

function renderBudgets(fixture: ApiEnvelope<ApiBudgets> = costBudgetsFixture()) {
  return render(
    <Harness client={clientReturning({ '/api/v1/cost/budgets': fixture })}>
      <BudgetsScreen />
    </Harness>,
  );
}

/** The fixture's first budget, as a budget rather than a possibly absent one. */
function base(): ApiBudget {
  const [first] = costBudgetsFixture().data.budgets;
  if (first === undefined) {
    throw new Error('the budgets fixture has no rows, so the cases below would be vacuous');
  }
  return first;
}

function withOne(budget: ApiBudget): ApiEnvelope<ApiBudgets> {
  const fixture = costBudgetsFixture();
  return { ...fixture, data: { ...fixture.data, budgets: [budget], unsupported: 0 } };
}

describe('BudgetsScreen', () => {
  it('draws the pace marker where the period has got to, not where the spend is', async () => {
    // The whole design claim. Ninety five percent spent is healthy on the twenty eighth and
    // alarming on the fourth, so the bar alone is not information: the tick is what makes the
    // fill mean something. Both are asserted because a tick at the same place as the fill
    // would look right and say nothing.
    renderBudgets();
    const bars = await screen.findAllByTestId('budget-bar');
    const [first] = bars;
    expect(first).toBeDefined();
    const fill = first?.querySelector('i');
    const pace = first?.querySelector('b');
    // 95.26 percent of the budget spent with 83.33 percent of the month gone, which is the
    // AT_RISK rule drawn rather than described.
    expect(fill).toHaveStyle({ width: '95.26%' });
    expect(pace).toHaveStyle({ left: '83.33%' });
  });

  it('says both percentages out loud for a reader who cannot see the bar', async () => {
    renderBudgets();
    const bars = await screen.findAllByTestId('budget-bar');
    expect(bars[0]).toHaveAttribute(
      'aria-label',
      '95% of the budget spent, 83% of the period elapsed',
    );
  });

  it('marks an overspent budget as over rather than as a full bar', async () => {
    // A bar clamped at a hundred percent looks identical to one that landed exactly on the
    // limit. The status and the colour are what separate them.
    renderBudgets();
    await screen.findAllByTestId('budget');
    const over = screen
      .getAllByTestId('budget')
      .find((card) => card.getAttribute('data-status') === 'OVER');
    expect(over).toBeDefined();
    expect(within(over as HTMLElement).getByTestId('budget-status')).toHaveTextContent('over');
    expect(over?.querySelector('i')).toHaveAttribute('data-over', 'true');
    // Clamped, so the fill never runs past its own track.
    expect(over?.querySelector('i')).toHaveStyle({ width: '100%' });
  });

  it('says a budget has no number rather than drawing it at nothing spent', async () => {
    // The failure this screen exists to prevent. A budget over a tag expression compared
    // against no spend is not a budget that is being underspent.
    renderBudgets();
    const untracked = await screen.findByTestId('budgets-untracked');
    const cards = within(untracked).getAllByTestId('budget');
    expect(cards).toHaveLength(2);
    for (const card of cards) {
      expect(within(card).getByTestId('budget-unknown')).toBeInTheDocument();
      // No bar at all, because an empty track is a claim about spend.
      expect(card.querySelector('[data-testid="budget-bar"]')).toBeNull();
    }
  });

  it('blames the scope when the scope is the thing we cannot compute', async () => {
    // One of two absences that need different actions. This one is never fixed by waiting: it
    // is a limit of the product, and ISS-210 records it.
    renderBudgets();
    const untracked = await screen.findByTestId('budgets-untracked');
    expect(within(untracked).getAllByTestId('budget-unknown')[0]).toHaveTextContent(
      /cannot reproduce/,
    );
  });

  it('blames the collection when the scope is one we do compute', async () => {
    // The other absence, and the reason the two sentences are not one sentence. This budget is
    // over the whole payer, which Meter computes perfectly well, so the missing number is a
    // collection that has not landed and the action is to wait or to look at the ingest run.
    // Its own test rather than a second render in the one above, because findAllBy resolves
    // against the first tree's cards the moment they exist and never waits for the second.
    const waiting: ApiBudget = { ...base(), scope: 'ALL', actual: null, used: null };
    renderBudgets(withOne(waiting));
    expect(await screen.findByTestId('budget-unknown')).toHaveTextContent(
      /not the same as nothing having been spent/,
    );
  });

  it('counts the budgets with no number instead of mixing them in', async () => {
    // A list of two statuses above ten blanks reads as an estate that is mostly fine.
    renderBudgets();
    expect(await screen.findByTestId('budgets-untracked-heading')).toHaveTextContent(
      '2 budgets with no number',
    );
    const tracked = screen.getByTestId('budgets-tracked');
    expect(within(tracked).getAllByTestId('budget')).toHaveLength(2);
  });

  it('says the period the comparison is against', async () => {
    // A budget figure with no period is a number nobody can check.
    renderBudgets();
    expect(await screen.findByTestId('budgets-period')).toHaveTextContent('2026-09-01');
  });

  it('never claims a limit was entered here', async () => {
    // Read only in v1, and a reader is entitled to know the limit is the provider's own.
    renderBudgets();
    expect(await screen.findByTestId('budgets-period')).toHaveTextContent(/never entered here/);
  });

  it('has no accessibility violations', async () => {
    const { container } = renderBudgets();
    await screen.findAllByTestId('budget');
    expect(await violationsIn(container)).toEqual([]);
  });
});
