import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { AccountsScreen } from '../AccountsScreen';
import { accountOf, clientReturning, metaOf } from './fixtures';
import { Harness } from './Harness';

const ACCOUNTS = [
  accountOf('111122223333', 'HEALTHY'),
  accountOf('444455556666', 'ACCESS_DENIED'),
  accountOf('777788889999', 'NOT_DEPLOYED'),
];

function renderScreen(envelope = { data: ACCOUNTS, meta: metaOf() }) {
  const client = clientReturning({ '/api/v1/accounts': envelope });
  return render(
    <Harness client={client}>
      <AccountsScreen />
    </Harness>,
  );
}

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
    const table = within(screen.getByRole('table'));
    expect(table.getByText(/access denied/)).toBeInTheDocument();
    expect(table.getByText(/not deployed/)).toBeInTheDocument();
  });

  it('says not yet collected rather than showing an empty success', async () => {
    renderScreen({ data: [], meta: metaOf({ as_of: null, collected_at: null }) });
    await waitFor(() => {
      expect(screen.getByTestId('state').dataset['state']).toBe('never-collected');
    });
  });

  it('shows a genuine empty with the filter that produced it', async () => {
    const user = userEvent.setup();
    renderScreen({ data: [accountOf('1', 'HEALTHY')], meta: metaOf() });
    await waitFor(() => {
      expect(screen.getByText('1')).toBeInTheDocument();
    });
    await user.click(screen.getByRole('button', { name: 'broken' }));
    expect(screen.getByTestId('state').dataset['state']).toBe('empty');
    expect(screen.getByText(/Broken/)).toBeInTheDocument();
  });

  it('reports a partial view rather than showing the rows alone', async () => {
    renderScreen({
      data: ACCOUNTS,
      meta: metaOf({ scope_coverage: { visible: 3, total: 9, is_partial: true } }),
    });
    await waitFor(() => {
      expect(screen.getByTestId('state').dataset['state']).toBe('partial');
    });
    expect(screen.getByText(/6 missing/)).toBeInTheDocument();
  });
});
