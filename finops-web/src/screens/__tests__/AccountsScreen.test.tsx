import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { AccountsScreen } from '../AccountsScreen';
import { costByAccountFixture } from '../../api/fixtures/cost';
import { accountOf, clientReturning, metaOf } from './fixtures';
import { Harness } from './Harness';

const ACCOUNTS = [
  accountOf('111122223333', 'HEALTHY'),
  accountOf('444455556666', 'ACCESS_DENIED'),
  accountOf('777788889999', 'NOT_DEPLOYED'),
];

function renderScreen(envelope = { data: ACCOUNTS, meta: metaOf() }) {
  const client = clientReturning({
    '/api/v1/accounts': envelope,
    '/api/v1/cost/by-account': costByAccountFixture(),
    '/api/v1/health/freshness': { data: FRESHNESS, meta: metaOf() },
  });
  return render(
    <Harness client={client}>
      <AccountsScreen />
    </Harness>,
  );
}

/** Each fixture account read by inventory an hour ago, against an hourly interval. */
const FRESHNESS = ACCOUNTS.map((account) => ({
  collector: 'inventory',
  scope_key: `${account.provider}:${account.account_id}`,
  as_of: '2026-08-27T08:00:00Z',
  cadence_seconds: 3600,
  age_seconds: 3600,
  state: 'current',
  cause: null,
  is_stale: false,
}));

/** The accounts read's own state, not the state of a chart beside it. */
function accountsState(): HTMLElement | undefined {
  return screen
    .getAllByTestId('state')
    .find((one) => one.closest('[data-testid^="chart-"]') === null);
}

describe('AccountsScreen, how fresh each account is', () => {
  it('draws each account by its collectors, the stalest first', async () => {
    renderScreen();
    const health = await screen.findByRole('region', { name: 'How fresh each account is' });
    await waitFor(() => {
      expect(health.querySelectorAll('[data-testid="heat-cell"]').length).toBeGreaterThan(0);
    });
    expect(health).toHaveTextContent(ACCOUNTS[0]?.name ?? 'an account');
  });
});

describe('AccountsScreen, where the money is', () => {
  it("ranks the accounts by this period's spend, the largest first", async () => {
    renderScreen();
    const largest = [...costByAccountFixture().data].sort(
      (left, right) => Number(right.effective_cost) - Number(left.effective_cost),
    )[0];
    const spend = await screen.findByRole('region', { name: 'Where the money is' });
    await waitFor(() => {
      expect(spend).toHaveTextContent(largest?.name ?? 'an account');
    });
  });
});

describe('AccountsScreen', () => {
  it('lists the accounts in scope', async () => {
    renderScreen();
    await waitFor(() => {
      expect(screen.getByText('111122223333')).toBeInTheDocument();
    });
  });

  it('finds every broken onboarding in one click', async () => {
    // One filter rather than four. Making somebody select four states in turn
    // is how a screen that technically supports the question fails to answer it.
    const user = userEvent.setup();
    renderScreen();
    await waitFor(() => {
      expect(screen.getByText('111122223333')).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: 'broken' }));
    expect(screen.queryByText('111122223333')).toBeNull();
    expect(screen.getByText('444455556666')).toBeInTheDocument();
    expect(screen.getByText('777788889999')).toBeInTheDocument();
  });

  it('filters to one health state as well', async () => {
    const user = userEvent.setup();
    renderScreen();
    await waitFor(() => {
      expect(screen.getByText('111122223333')).toBeInTheDocument();
    });
    await user.click(screen.getByRole('button', { name: 'not deployed' }));
    expect(screen.getByText('777788889999')).toBeInTheDocument();
    expect(screen.queryByText('444455556666')).toBeNull();
  });

  it('shows the provider words for a broken role rather than a code', async () => {
    // Two of the three are broken, and each says why in the provider's own
    // words so nobody has to open a log to act on it.
    renderScreen();
    await waitFor(() => {
      expect(screen.getAllByText(/the trust policy names another principal/)).toHaveLength(2);
    });
    // Scoped to the table, because the filter controls carry the same words.
    const table = within(screen.getByRole('table', { name: 'Accounts in scope' }));
    expect(table.getByText(/access denied/)).toBeInTheDocument();
    expect(table.getByText(/not deployed/)).toBeInTheDocument();
  });

  it('says not yet collected rather than showing an empty success', async () => {
    renderScreen({ data: [], meta: metaOf({ as_of: null, collected_at: null }) });
    await waitFor(() => {
      expect(accountsState()?.dataset['state']).toBe('never-collected');
    });
  });

  it('shows a genuine empty with the filter that produced it', async () => {
    const user = userEvent.setup();
    renderScreen({ data: [accountOf('1', 'HEALTHY')], meta: metaOf() });
    await waitFor(() => {
      expect(screen.getByText('1')).toBeInTheDocument();
    });
    await user.click(screen.getByRole('button', { name: 'broken' }));
    expect(accountsState()?.dataset['state']).toBe('empty');
    expect(screen.getByText(/Broken/)).toBeInTheDocument();
  });

  it('reports a partial view rather than showing the rows alone', async () => {
    renderScreen({
      data: ACCOUNTS,
      meta: metaOf({
        scope_coverage: { visible: 3, total: 9, is_partial: true, unit: 'accounts' },
      }),
    });
    await waitFor(() => {
      expect(accountsState()?.dataset['state']).toBe('partial');
    });
    expect(screen.getByText(/6 missing/)).toBeInTheDocument();
  });
});
