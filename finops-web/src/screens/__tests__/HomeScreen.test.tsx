import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { ArrivingRail, HomeScreen, type SlotDef } from '../HomeScreen';
import { PERSONA_KEY } from '../personas';
import { Harness } from './Harness';
import { clientReturning, exploreOf, metaOf } from './fixtures';
import { costBudgetsFixture } from '../../api/fixtures/cost';
import { violationsIn } from '../../components/__tests__/axe';
import type { ApiClient } from '../../api/client';
import type { ApiEnvelope } from '../../api/types';

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

function renderHome(
  answers: Readonly<Record<string, ApiEnvelope<unknown>>> = {},
  client: ApiClient = clientReturning({ '/api/v1/platform/cost': COST, ...answers }),
) {
  return render(
    <Harness client={client}>
      <HomeScreen />
    </Harness>,
  );
}

/** One KPI tile, by the label it carries. */
function tile(label: string): HTMLElement {
  return screen.getByRole('region', { name: label });
}

async function meterCostShown(): Promise<void> {
  await waitFor(() => {
    expect(within(tile('Meter cost, this month')).getByTestId('kpi-value')).toHaveTextContent(
      '$431.00',
    );
  });
}

// This environment supplies a localStorage with no methods on it, so a working store is
// installed for each case, as theme.test.ts and App.test.tsx do.
const original = Object.getOwnPropertyDescriptor(window, 'localStorage');
const stored = new Map<string, string>();

beforeEach(() => {
  stored.clear();
  Object.defineProperty(window, 'localStorage', {
    value: {
      getItem: (key: string) => stored.get(key) ?? null,
      setItem: (key: string, value: string) => {
        stored.set(key, value);
      },
    },
    configurable: true,
  });
});

afterEach(() => {
  if (original) {
    Object.defineProperty(window, 'localStorage', original);
  }
});

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
    // Scheduled reports say they arrive with P8, which is true while TASK-P8-011 is unbuilt.
    // A promise naming a sub project that has shipped is the failure this guards.
    const { container } = renderHome();
    expect(screen.queryByTestId('home-rail')).toBeNull();
    expect(container).not.toHaveTextContent(/arrives with P[1-7]\b/);
    expect(container).not.toHaveTextContent(/\bP3\b/);
  });

  it('links its spend to the screen that owns it', () => {
    renderHome();
    expect(screen.getByRole('link', { name: 'Effective Cost' })).toHaveAttribute(
      'href',
      '/analyze/explorer',
    );
    expect(screen.getByRole('link', { name: /Meter cost/ })).toHaveAttribute(
      'href',
      '/platform/cost',
    );
  });

  it('shows Meter own cost as a measured figure, summed across modules', async () => {
    renderHome();
    // 412.80 plus the unallocated 18.20. Unallocated is a module like any other.
    await meterCostShown();
    expect(tile('Meter cost, this month')).toHaveAttribute('data-provenance', 'measured');
  });

  it('requests nothing that the screens it summarises do not already request', async () => {
    // Home owns no data of its own. A home screen with its own query will one day disagree
    // with the screen it summarises, so every route here belongs to a screen that reads it.
    const asked: string[] = [];
    const inner = clientReturning({ '/api/v1/platform/cost': COST });
    const recording: ApiClient = {
      post: <T,>(path: string) => inner.post<T>(path),
      patch: () => Promise.reject(new Error('no patch stub')),
      delete: () => Promise.reject(new Error('no delete stub')),
      getFile: (path: string) => inner.getFile(path),
      get: <T,>(path: string) => {
        asked.push(path);
        return inner.get<T>(path);
      },
    };
    renderHome({}, recording);
    await meterCostShown();
    expect([...new Set(asked.map((path) => path.split('?')[0]))].sort()).toEqual([
      // `useCostAllocation`, the allocation screen's own hook, by its default tag.
      '/api/v1/cost/allocation',
      // `useCostAnomalies`, the anomalies screen's own hook.
      '/api/v1/cost/anomalies',
      // `useBudgets`, the budgets screen's own hook.
      '/api/v1/cost/budgets',
      // `useCostCommitments`, the commitments screen's own hook.
      '/api/v1/cost/commitments',
      // `useCostExplore`, Cost Explorer's own hook, with views written as the Explorer writes
      // them: its own default view, and the last thirty days by service category.
      '/api/v1/cost/explore',
      // `useCostForecast`, the forecast screen's own hook.
      '/api/v1/cost/forecast',
      '/api/v1/platform/cost',
      // `useRecommendations`, the recommendations screen's own hook.
      '/api/v1/waste/recommendations',
    ]);
    // The Explorer's own default view, under its own key, so the two share one answer.
    expect(asked).toContain('/api/v1/cost/explore');
  });

  it('shows the budget furthest ahead of its calendar, not the biggest one', async () => {
    renderHome({ '/api/v1/cost/budgets': costBudgetsFixture() });
    const budget = tile('Budget consumed');
    await waitFor(() => {
      expect(within(budget).getByTestId('kpi-value')).toHaveTextContent('106.7%');
    });
    expect(within(budget).getByTestId('kpi-note')).toHaveTextContent(
      '83.3% of the period gone, Platform team, worst of 4 budgets, 2 with no number',
    );
  });

  it('says why a figure the data cannot support has none', async () => {
    const withoutListCost = {
      data: exploreOf({ metrics_available: ['effective_cost', 'billed_cost'] }),
      meta: metaOf(),
    };
    renderHome({ '/api/v1/cost/explore': withoutListCost });
    const rate = tile('Effective savings rate');
    expect(await within(rate).findByTestId('kpi-unsupported')).toHaveTextContent(
      'The bill carries no List Cost',
    );
    expect(within(rate).queryByTestId('kpi-value')).toBeNull();
  });

  it('shows a read that failed as a failure, never as a figure not yet collected', async () => {
    renderHome();
    const forecast = tile('Forecast, month end');
    await waitFor(() => {
      expect(forecast.querySelector("[data-state='failed']")).not.toBeNull();
    });
    expect(forecast).not.toHaveTextContent(/not yet collected/i);
    expect(within(forecast).queryByTestId('kpi-value')).toBeNull();
  });

  it('opens on the dashboard as drawn, and remembers the one the reader chose', () => {
    const { unmount } = renderHome();
    expect(screen.getByRole('radio', { name: 'FinOps practitioner' })).toBeChecked();

    fireEvent.click(screen.getByRole('radio', { name: 'Executive' }));
    expect(tile('Top movers')).toBeInTheDocument();
    expect(stored.get(PERSONA_KEY)).toBe('executive');

    unmount();
    renderHome();
    expect(screen.getByRole('radio', { name: 'Executive' })).toBeChecked();
  });

  it('gives the Engineering lead the query cost of the dashboards', () => {
    renderHome();
    fireEvent.click(screen.getByRole('radio', { name: 'Engineering lead' }));
    expect(screen.getByRole('link', { name: /Top findings by dollar/ })).toHaveAttribute(
      'href',
      '/govern/query-cost',
    );
    // Meter's own cost stays on the front page whichever dashboard is open, constraint 7.
    expect(tile('Meter cost, this month')).toBeInTheDocument();
  });

  it('has no accessibility violations', async () => {
    const { container } = renderHome();
    await meterCostShown();
    expect(await violationsIn(container)).toEqual([]);
  });
});
