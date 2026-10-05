import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ArrivingRail, HomeScreen, type SlotDef } from '../HomeScreen';
import { Harness } from './Harness';
import { clientReturning, metaOf } from './fixtures';
import { costBudgetsFixture } from '../../api/fixtures/cost';
import { violationsIn } from '../../components/__tests__/axe';
import type { ApiClient } from '../../api/client';

const COST = {
  data: [
    {
      day: '2026-09-05',
      module: 'api',
      service: 'AmazonECS',
      amortized_cost: '412.80',
      as_of: '2026-09-05T04:00:00Z',
      collected_at: '2026-09-06T09:54:00Z',
    },
    {
      day: '2026-09-05',
      module: 'unallocated',
      service: 'AmazonEC2',
      amortized_cost: '18.20',
      as_of: '2026-09-05T04:00:00Z',
      collected_at: '2026-09-06T09:54:00Z',
    },
  ],
  meta: metaOf(),
};

function renderHome(client: ApiClient = clientReturning({ '/api/v1/platform/cost': COST })) {
  return render(
    <Harness client={client}>
      <HomeScreen />
    </Harness>,
  );
}

describe('the arriving rail', () => {
  // The mechanism, tested against a synthetic slot. Home has none left to fill today, and a
  // test that counted Home's own slots would throw on an empty page rather than test anything.
  // The claim is about what a slot says when one exists.
  const EXAMPLE: SlotDef = {
    id: 'example',
    label: 'An example figure',
    owns: '/cost',
    arrives: 'P9 Example',
  };

  function renderRail(slots: readonly SlotDef[]) {
    return render(
      <Harness client={clientReturning({})}>
        <ArrivingRail slots={slots} />
      </Harness>,
    );
  }

  it('names the sub project that will fill an empty slot', () => {
    renderRail([EXAMPLE]);
    const slot = screen.getByTestId('home-slot-example');
    expect(slot).toHaveTextContent(/not yet collected/i);
    expect(slot).toHaveTextContent('P9 Example');
  });

  it('renders no figure and no currency in an empty slot', () => {
    // Rule 5 of 12-UI-DESIGN: an absence is never a number. Asserted as "no Figure
    // and no currency" rather than "no digit", because the slot names the sub project
    // and P9 legitimately contains one.
    renderRail([EXAMPLE]);
    const slot = screen.getByTestId('home-slot-example');
    expect(slot.querySelector('[data-testid="figure"]')).toBeNull();
    expect(slot).not.toHaveTextContent('$');
  });

  it('links a slot to the screen that will own it', () => {
    renderRail([EXAMPLE]);
    expect(screen.getByRole('link', { name: 'P9 Example' })).toHaveAttribute('href', '/cost');
  });

  it('draws nothing when nothing is still to arrive, not a heading over nothing', () => {
    const { container } = renderRail([]);
    expect(screen.queryByTestId('home-rail')).toBeNull();
    expect(container).not.toHaveTextContent(/not yet collected/i);
  });
});

describe('HomeScreen', () => {
  it('promises nothing that has already shipped', () => {
    // Realized savings said it would arrive with P3 after P3 shipped and /waste/savings was
    // built, the same failure the P1 slots had. With it gone nothing is still to arrive, so
    // the rail is not drawn at all.
    const { container } = renderHome();
    expect(screen.queryByTestId('home-rail')).toBeNull();
    expect(container).not.toHaveTextContent(/arrives with/i);
    expect(container).not.toHaveTextContent(/\bP3\b/);
  });

  it('shows the spend P1 filled rather than still promising it', () => {
    // The defect this replaces was on the front page of a demo: three slots saying
    // total spend and trend arrive with P1, on a build where /cost shows both. A
    // product that does not know what it has is worse than one that never mentioned
    // the feature.
    renderHome();
    expect(screen.queryByText(/P1 Cost Intelligence/)).toBeNull();
    expect(screen.getByRole('link', { name: /Effective Cost/ })).toHaveAttribute(
      'href',
      '/analyze/explorer',
    );
  });

  it('gives every slot a link to the screen that owns it', () => {
    renderHome();
    expect(screen.getByRole('link', { name: /Meter cost/ })).toHaveAttribute(
      'href',
      '/platform/cost',
    );
    // The findings slot is filled since TASK-P2-021, so its link is the slot
    // heading rather than the name of a sub project that has not arrived.
    expect(screen.getByRole('link', { name: /Top findings by dollar/ })).toHaveAttribute(
      'href',
      '/govern/query-cost',
    );
  });

  it('shows Meter own cost as a measured figure, summed across modules', async () => {
    renderHome();
    // 412.80 plus the unallocated 18.20. Unallocated is a module like any other.
    expect(await screen.findByText('$431.00')).toBeInTheDocument();
  });

  it('requests nothing that the screens it summarises do not already request', async () => {
    // Home owns no data of its own. A home screen with its own query will one
    // day disagree with the screen it summarises.
    const asked: string[] = [];
    const inner = clientReturning({ '/api/v1/platform/cost': COST });
    const recording: ApiClient = {
      post: <T,>(path: string) => inner.post<T>(path),
      getFile: (path: string) => inner.getFile(path),
      get: <T,>(path: string) => {
        asked.push(path);
        return inner.get<T>(path);
      },
    };
    renderHome(recording);
    await screen.findByText('$431.00');
    // Every path belongs to a screen that already requests it, through that
    // screen's own hook and its own query key: `usePlatformCost`,
    // `useQueryFindings`, `useQueryGroups` and `useQuerySurfaces`. The rule is
    // that Home has no query of its own, not that it makes one request. A path
    // appearing here that no other screen owns is the failure this guards.
    expect([...asked].sort()).toEqual([
      // `useBudgets`, the budgets screen's own hook and its own key. Home shows the one
      // budget running furthest ahead of its calendar, which is a ranking over the rows that
      // screen already holds rather than a slice of its own. FEAT-060.
      '/api/v1/cost/budgets',
      // `useCostSummary`, which is the spend screen's own hook. Home shows the total
      // and the change; it computes neither.
      '/api/v1/cost/summary',
      // `useCostTrend`, the same hook and the same query key CostScreen uses. Added with the
      // chart on the spend card: the headline figure says what this period cost and the shape
      // says what happened inside it, and the seeded estate's last day is half as expensive
      // again as the one before, which is invisible in a figure and unmissable in a picture.
      '/api/v1/cost/trend',
      '/api/v1/platform/cost',
      '/api/v1/query/findings',
      '/api/v1/query/groups',
      '/api/v1/query/instances',
      // `useRecommendations`, which is the recommendations screen's own hook, added with
      // FEAT-052's Top actions panel. The panel summarises exactly the rows `/waste` shows
      // and ranks them the same way, which is why it reuses the key rather than asking for
      // its own slice.
      '/api/v1/waste/recommendations',
    ]);
  });

  it('picks the budget furthest ahead of its calendar, not the biggest one', async () => {
    // FEAT-060. The ranking is the only arithmetic this screen does for the tile, so it is the
    // only thing here that can be wrong. Ranking by limit would put the 40,000 EC2 hours budget
    // first, and it has no number at all. Ranking by amount spent would put the 11,908 payer
    // wide budget first, and it is still inside its limit. The one that needs somebody today is
    // the 6,402 against 6,000, because it is already over with a sixth of the month left.
    renderHome(
      clientReturning({
        '/api/v1/platform/cost': COST,
        '/api/v1/cost/budgets': costBudgetsFixture(),
      }),
    );
    expect(await screen.findByTestId('home-budget-figure')).toHaveTextContent('$6,402');
    const tile = screen.getByLabelText('Budget');
    expect(tile).toHaveTextContent('Platform team');
    // And the card never reads as the whole position: three others exist, two of them unscored.
    expect(screen.getByTestId('home-budget-count')).toHaveTextContent(
      'worst of 4 budgets, 2 with no number',
    );
  });

  it('has no accessibility violations', async () => {
    const { container } = renderHome();
    await screen.findByText('$431.00');
    expect(await violationsIn(container)).toEqual([]);
  });
});
