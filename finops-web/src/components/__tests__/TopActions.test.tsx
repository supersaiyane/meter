import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { describe, expect, it } from 'vitest';

import { recommendationsFixture } from '../../api/fixtures/waste';
import type { ApiRecommendation } from '../../api/types';
import { TopActions } from '../TopActions';
import { riskLabel } from '../actionRisk';
import { violationsIn } from './axe';

/**
 * FEAT-052. The panel that answers what to do this morning.
 *
 * The cases that carry this file are about the second group and the labels, not about the
 * ranking. Ranking by money is ADR-0016 and is tested where the severity band is. What is new
 * here is the claim that a reader can tell an easy win from a permanent deletion, and the
 * failure being guarded is a panel that flags something irreversible as low risk because
 * nothing was running on it.
 */

const FRESHNESS = {
  asOf: new Date('2026-08-27T09:00:00Z'),
  collectedAt: new Date('2026-08-27T09:30:00Z'),
};

function rows(): readonly ApiRecommendation[] {
  return recommendationsFixture().data.recommendations;
}

/**
 * The fixture's first row, as a row rather than as a possibly absent one.
 *
 * Indexing the array gives `ApiRecommendation | undefined`, and spreading that produces an
 * object whose every field is optional, which is not the type the panel takes. Throwing here
 * rather than asserting non null says what an empty fixture would actually mean: every case
 * below that builds on this row would pass without testing anything.
 */
function base(): ApiRecommendation {
  const [first] = rows();
  if (first === undefined) {
    throw new Error('the waste fixture has no rows, so the cases below would be vacuous');
  }
  return first;
}

function renderPanel(recommendations: readonly ApiRecommendation[] = rows()) {
  return render(
    <MemoryRouter>
      <TopActions recommendations={recommendations} freshness={FRESHNESS} />
    </MemoryRouter>,
  );
}

describe('TopActions', () => {
  it('ranks the biggest saving first', async () => {
    renderPanel();
    const saving = screen.getByTestId('top-actions-saving');
    const cells = await within(saving).findAllByRole('rowheader');
    // The 412.64 rightsizing outranks the 188.20 Graviton candidate, which is the same order
    // the recommendations screen uses.
    expect(cells[0]).toHaveTextContent('Rightsizing');
  });

  it('separates the no regret group from the biggest saving group', () => {
    renderPanel();
    const noRegret = screen.getByTestId('top-actions-no-regret');
    // The alarm, which is reversible and stops nothing. It is also the smallest money on the
    // list, which is the point of the group being separate rather than a boost.
    expect(noRegret).toHaveTextContent('Alarm with insufficient data');
    expect(noRegret).not.toHaveTextContent('Rightsizing');
  });

  it('calls an irreversible finding permanent even though nothing is running', () => {
    // The failure this panel exists to prevent, and the row is built here rather than taken
    // from the fixture. The fixture's unattached volume is DONE on purpose, because that is
    // the lifecycle case the recommendations screen needs, and a panel test leaning on it
    // would have been asserting against a row the open filter correctly removes.
    const permanent: ApiRecommendation = {
      ...base(),
      recommendation_id: 'b1c2d3e4-f5a6-4b7c-8d9e-0f1a2b3c4d5e',
      waste_class: 'EBS_UNATTACHED',
      resource_id: 'vol-0a1b2c3d',
      lifecycle: 'OPEN',
      estimated_monthly_saving: '64.0000',
      reversible: false,
      disturbs_running_work: false,
      is_no_regret: false,
      risk_why: 'Deleting a volume is final. It is attached to nothing, so nothing stops.',
    };
    renderPanel([permanent]);
    const saving = screen.getByTestId('top-actions-saving');
    expect(saving).toHaveTextContent('Unattached volume');
    expect(saving).toHaveTextContent('permanent');
    // And not among the easy wins, which is the whole claim.
    expect(screen.getByTestId('top-actions-no-regret-empty')).toBeInTheDocument();
  });

  it('shows the sentence as well as the label', () => {
    // The label is what a reader scans and the sentence is what they decide on. A label with
    // no sentence behind it is one nobody can argue with.
    renderPanel();
    // Scoped to one group, because a finding qualifying for both appears twice and that is
    // correct: no regret is a filter over the same rows, not a different list.
    const saving = screen.getByTestId('top-actions-saving');
    expect(
      within(saving).getByText(/never left insufficient data has never fired/),
    ).toBeInTheDocument();
    expect(within(saving).getByText(/A resize needs a stop and a start/)).toBeInTheDocument();
  });

  it('leaves a finding that is not open out of both groups', () => {
    // The fixture already exercises this: its Graviton candidate is ACCEPTED and its
    // unattached volume is DONE, so only two of its four rows are work.
    renderPanel();
    const saving = screen.getByTestId('top-actions-saving');
    expect(saving).not.toHaveTextContent('GRAVITON_CANDIDATE');
    expect(saving).not.toHaveTextContent('Unattached volume');
    // Two of the fixture's four rows are work, and the group shows both, so the caption says
    // so rather than implying something was held back.
    expect(saving).toHaveTextContent('All 2');
  });

  it('shows nothing at all when every finding is closed', () => {
    const closed = rows().map((row) => ({ ...row, lifecycle: 'ACCEPTED' }));
    renderPanel(closed);
    expect(screen.getByTestId('top-actions-saving-empty')).toBeInTheDocument();
    expect(screen.getByTestId('top-actions-no-regret-empty')).toBeInTheDocument();
  });

  it('says an empty group is an answer rather than rendering blank', () => {
    // Rule 5 of docs/12-UI-DESIGN.md applied to an absence. A blank panel reads as broken.
    renderPanel([]);
    expect(screen.getByTestId('top-actions-no-regret-empty')).toHaveTextContent(
      /an answer rather than a gap/,
    );
  });

  it('names the category it does not have', () => {
    // Their widget has a performance category. We have no performance dimension at all, and a
    // reader is entitled to know the two groups are not the whole picture.
    renderPanel();
    expect(screen.getByTestId('top-actions-absent')).toHaveTextContent(/never what is starved/);
  });

  it('marks every saving as modelled, never measured', () => {
    renderPanel();
    const figures = screen.getAllByTestId('figure');
    expect(figures.length).toBeGreaterThan(0);
    for (const figure of figures) {
      expect(figure).toHaveAttribute('data-provenance', 'modelled');
    }
  });

  it('has no accessibility violations', async () => {
    const { container } = renderPanel();
    expect(await violationsIn(container)).toEqual([]);
  });
});

describe('riskLabel', () => {
  function row(reversible: boolean, disturbs: boolean): ApiRecommendation {
    return {
      ...base(),
      reversible,
      disturbs_running_work: disturbs,
      is_no_regret: reversible && !disturbs,
    };
  }

  it('leads with permanent, because that is the half a reader must not miss', () => {
    expect(riskLabel(row(false, false))).toBe('permanent');
    expect(riskLabel(row(false, true))).toBe('permanent, interrupts the workload');
  });

  it('says no regret only when both halves hold', () => {
    expect(riskLabel(row(true, false))).toBe('no regret');
    expect(riskLabel(row(true, true))).toBe('interrupts the workload');
  });
});
