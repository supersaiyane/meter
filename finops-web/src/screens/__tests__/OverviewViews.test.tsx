import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import type { ApiClient } from '../../api/client';
import {
  costAllocationFixture,
  costAnomaliesFixture,
  costBudgetsFixture,
  costByAccountFixture,
  costCommitmentsFixture,
} from '../../api/fixtures/cost';
import {
  queryFindingsFixture,
  queryGroupsFixture,
  surfaceInstancesFixture,
} from '../../api/fixtures/query';
import { recommendationsFixture } from '../../api/fixtures/waste';
import type {
  ApiEnvelope,
  ApiRecommendation,
  ApiSchedule,
  ApiSchedules,
} from '../../api/types';
import { wasteClassName } from '../../components/displayNames';
import { HomeScreen } from '../HomeScreen';
import { RIGHTSIZING } from '../overviewKpis';
import { Harness } from './Harness';
import { exploreOf, forecastOf, metaOf } from './fixtures';

/**
 * The three dashboards with an estate behind them, FEAT-070: each shows what the screens it reads
 * hold. `HomeScreen.test.tsx` covers the frame and the reads that fail; this covers the figures.
 */

const SCHEDULE: ApiSchedule = {
  schedule_id: 's-1',
  view_id: 'v-1',
  view_name: 'Active accounts',
  screen_path: '/inventory/accounts',
  export_path: '/api/v1/accounts',
  format: 'xlsx',
  cadence: 'WEEKLY',
  recipients: ['dev@example.local'],
  enabled: true,
  next_run_at: '2026-10-12T06:00:00Z',
  created_at: '2026-10-07T09:00:00Z',
  updated_at: '2026-10-07T09:00:00Z',
};

/** Four schedules, so the panel's three are a choice: one paused, three that will run. */
const SCHEDULES: ApiSchedules = {
  rendering: true,
  retention: 'Files are kept until a retention period is decided, OPEN-15.',
  delivery: 'Nothing is sent yet: where reports go is OPEN-11.',
  schedules: [
    {
      ...SCHEDULE,
      schedule_id: 's-later',
      view_name: 'Cost by region',
      cadence: 'MONTH_CLOSE',
      next_run_at: '2026-11-06T06:00:00Z',
    },
    {
      ...SCHEDULE,
      schedule_id: 's-last',
      view_name: 'Last',
      next_run_at: '2026-12-01T06:00:00Z',
    },
    SCHEDULE,
    {
      ...SCHEDULE,
      schedule_id: 's-paused',
      view_name: null,
      enabled: false,
      next_run_at: '2026-12-31T06:00:00Z',
    },
  ],
};

const ESTATE: Readonly<Record<string, ApiEnvelope<unknown>>> = {
  '/api/v1/reports/schedules': { data: SCHEDULES, meta: metaOf() },
  '/api/v1/platform/cost': { data: [], meta: metaOf() },
  '/api/v1/cost/explore': { data: exploreOf(), meta: metaOf() },
  '/api/v1/commitments/savings-rate?months=12': {
    data: {
      months: [
        {
          period: '2026-08-01',
          effective_cost: '4512.71',
          list_cost: '6000.00',
          rate: '0.2479',
          rate_basis: 'measured',
          lines: 120,
          lines_without_list_cost: 0,
          effective_cost_without_list_cost: '0',
          reason: null,
        },
      ],
    },
    meta: metaOf(),
  },
  '/api/v1/cost/forecast': { data: forecastOf(), meta: metaOf() },
  '/api/v1/cost/budgets': costBudgetsFixture(),
  '/api/v1/cost/allocation': costAllocationFixture(),
  '/api/v1/cost/commitments': costCommitmentsFixture(),
  '/api/v1/cost/anomalies': costAnomaliesFixture(),
  '/api/v1/cost/by-account': costByAccountFixture(),
  '/api/v1/waste/recommendations': recommendationsFixture(),
  '/api/v1/query/findings': queryFindingsFixture(),
  '/api/v1/query/groups': queryGroupsFixture(),
  '/api/v1/query/instances': surfaceInstancesFixture(),
};

/** Answers that replace the estate's for one case. A null answer makes that read fail. */
type Changes = Readonly<Record<string, ApiEnvelope<unknown> | null>>;

/** Answers a path, or failing that its route, so the dated Explorer views resolve too. */
function estateClient(changes: Changes = {}): ApiClient {
  const answers: Changes = { ...ESTATE, ...changes };
  return {
    get: <T,>(path: string): Promise<ApiEnvelope<T>> => {
      const answer = answers[path] ?? answers[path.split('?')[0] ?? path];
      return answer === undefined || answer === null
        ? Promise.reject(new Error(`no stub: ${path}`))
        : Promise.resolve(answer as ApiEnvelope<T>);
    },
    put: () => Promise.reject(new Error('no put stub')),
    patch: () => Promise.reject(new Error('no patch stub')),
    delete: () => Promise.reject(new Error('no delete stub')),
    getFile: () => Promise.reject(new Error('no file stub')),
    post: () => Promise.reject(new Error('no write stub')),
  };
}

// This environment supplies a localStorage with no methods on it, so a working store is
// installed for each case, as theme.test.ts and App.test.tsx do.
const original = Object.getOwnPropertyDescriptor(window, 'localStorage');

beforeEach(() => {
  const stored = new Map<string, string>();
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

function open(persona?: 'Executive' | 'Engineering lead', changes: Changes = {}) {
  render(
    <Harness client={estateClient(changes)}>
      <HomeScreen />
    </Harness>,
  );
  if (persona !== undefined) {
    fireEvent.click(screen.getByRole('radio', { name: persona }));
  }
}

const region = (name: string) => screen.getByRole('region', { name });

describe('the FinOps practitioner dashboard, as drawn', () => {
  it('shows the month to date spend and the savings rate against the on demand equivalent', async () => {
    open();
    await waitFor(() => {
      expect(within(region('Effective Cost')).getByTestId('kpi-value')).toHaveTextContent(
        '$4,513',
      );
    });
    await waitFor(() => {
      expect(
        within(region('Effective savings rate')).getByTestId('kpi-value'),
      ).toHaveTextContent('24.8%');
    });
    expect(within(region('Commitment coverage')).getByTestId('kpi-note')).toHaveTextContent(
      /^Utilization/,
    );
  });

  it('draws the daily chart with the estate budget pace, and shows unallocated spend', async () => {
    open();
    const daily = region('Daily Effective Cost');
    await waitFor(() => {
      expect(daily.querySelector('svg')).not.toBeNull();
    });
    expect(within(daily).queryByTestId('overview-no-pace')).toBeNull();
    await waitFor(() => {
      expect(within(region('Showback by team')).getByText('Unallocated')).toBeInTheDocument();
    });
  });

  it('lists the worst anomalies first', async () => {
    open();
    const services = await within(region('Anomalies')).findAllByTestId(
      'overview-anomaly-service',
    );
    expect(services.map((one) => one.textContent)).toEqual(['AmazonEC2', 'AmazonCloudWatch']);
  });

  it('ranks the open recommendations by modelled saving, and marks every saving modelled', async () => {
    const all = recommendationsFixture().data.recommendations;
    const largest = all
      .filter((one) => one.lifecycle === 'OPEN')
      .sort(
        (left, right) =>
          Number(right.estimated_monthly_saving) - Number(left.estimated_monthly_saving),
      )
      .slice(0, 3);
    open();
    const items = await within(region('Top recommendations')).findAllByRole('listitem');
    expect(items).toHaveLength(largest.length);
    items.forEach((item, index) => {
      expect(item).toHaveTextContent(largest[index]?.resource_id ?? 'a recommendation');
      expect(within(item).getByTestId('figure')).toHaveAttribute('data-provenance', 'modelled');
    });
    // What was already accepted or done is not a saving still to be had.
    for (const one of all.filter((each) => each.lifecycle !== 'OPEN')) {
      expect(region('Top recommendations')).not.toHaveTextContent(one.resource_id);
    }
  });

  it('says so when no recommendation is open', async () => {
    open(undefined, {
      '/api/v1/waste/recommendations': { data: { recommendations: [] }, meta: metaOf() },
    });
    expect(
      await within(region('Top recommendations')).findByText('No recommendation is open'),
    ).toBeInTheDocument();
  });

  it('says no budget covers every account only once the budgets were read', async () => {
    const budgets = costBudgetsFixture();
    const departmental = {
      ...budgets,
      data: {
        ...budgets.data,
        budgets: budgets.data.budgets.filter((one) => one.scope !== 'ALL'),
      },
    };
    open(undefined, { '/api/v1/cost/budgets': departmental });
    expect(
      await within(region('Daily Effective Cost')).findByTestId('overview-no-pace'),
    ).toBeInTheDocument();
  });

  it('says nothing about budgets it could not read', async () => {
    open(undefined, { '/api/v1/cost/budgets': null });
    await waitFor(() => {
      expect(region('Budget consumed').querySelector("[data-state='failed']")).not.toBeNull();
    });
    expect(within(region('Daily Effective Cost')).queryByTestId('overview-no-pace')).toBeNull();
  });

  it('lists the scheduled reports, a paused one first and then the next to run', async () => {
    open();
    const panel = within(region('Scheduled reports'));
    const items = await panel.findAllByRole('listitem');
    expect(items.map((item) => [...item.children].map((part) => part.textContent))).toEqual([
      ['A view you can no longer open', 'Weekly', 'Paused'],
      ['Active accounts', 'Weekly', '2026-10-12 06:00 UTC'],
      ['Cost by region', 'When the month closes', '2026-11-06 06:00 UTC'],
    ]);
    expect(panel.getByRole('link', { name: 'Scheduled reports' })).toHaveAttribute(
      'href',
      '/report/scheduled',
    );
    expect(region('Scheduled reports')).not.toHaveTextContent(/arrives with/);
  });

  it('says where a schedule is made when there is none', async () => {
    open(undefined, {
      '/api/v1/reports/schedules': { data: { ...SCHEDULES, schedules: [] }, meta: metaOf() },
    });
    const none = await within(region('Scheduled reports')).findByTestId(
      'overview-scheduled-none',
    );
    expect(within(none).getByRole('link', { name: 'Report Library' })).toHaveAttribute(
      'href',
      '/report/library',
    );
  });

  it('fails the schedules as a failure, never as none', async () => {
    open(undefined, { '/api/v1/reports/schedules': null });
    await waitFor(() => {
      expect(region('Scheduled reports').querySelector("[data-state='failed']")).not.toBeNull();
    });
    expect(
      within(region('Scheduled reports')).queryByTestId('overview-scheduled-none'),
    ).toBeNull();
  });
});

describe('the Executive dashboard', () => {
  it('names the top movers, the top accounts and where savings could come from', async () => {
    open('Executive');
    const movers = await within(region('Top movers')).findByTestId('overview-movers');
    expect(movers).toHaveTextContent('AmazonEC2');
    await waitFor(() => {
      expect(region('Top 10 accounts')).toHaveTextContent('fake-platform-a');
    });
    await waitFor(() => {
      expect(region('Savings available by category')).toHaveTextContent('Rightsizing');
    });
    // The fixture's Graviton migration was accepted and its unattached volume is done.
    expect(region('Savings available by category')).not.toHaveTextContent(
      wasteClassName('GRAVITON_CANDIDATE'),
    );
    expect(region('Savings available by category')).not.toHaveTextContent(
      wasteClassName('EBS_UNATTACHED'),
    );
    expect(region('Effective Cost by service, 12 months').querySelector('svg')).not.toBeNull();
    expect(region('This month against the forecast').querySelector('svg')).not.toBeNull();
  });
});

describe('the Engineering lead dashboard', () => {
  it('lists the rightsizing in scope and the query cost of the dashboards', async () => {
    const recommendations = recommendationsFixture().data.recommendations;
    const shown = (one: ApiRecommendation) =>
      one.lifecycle === 'OPEN' && RIGHTSIZING.has(one.waste_class);
    const resized = recommendations.filter(shown);
    const removed = recommendations.filter((one) => !shown(one));
    // The fixture holds open rightsizing, rightsizing already accepted and other kinds, so both
    // filters are tested rather than assumed.
    expect(resized.length).toBeGreaterThan(0);
    expect(removed.some((one) => RIGHTSIZING.has(one.waste_class))).toBe(true);
    expect(removed.some((one) => !RIGHTSIZING.has(one.waste_class))).toBe(true);

    open('Engineering lead');
    const rightsizing = region('Rightsizing');
    await waitFor(() => {
      for (const one of resized) {
        expect(rightsizing).toHaveTextContent(one.resource_id);
      }
    });
    for (const one of removed) {
      expect(rightsizing).not.toHaveTextContent(one.resource_id);
    }
    await waitFor(() => {
      expect(region('Where this month went').querySelector('svg')).not.toBeNull();
    });
    expect(screen.getByRole('link', { name: 'Open findings' })).toHaveAttribute(
      'href',
      '/govern/query-cost',
    );
    // FEAT-052's Top actions moved here from the single front page.
    expect(screen.getByTestId('top-actions')).toBeInTheDocument();
  });
});
