import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { HomeScreen } from '../HomeScreen';
import { Harness } from './Harness';
import { clientReturning, metaOf } from './fixtures';
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

describe('HomeScreen', () => {
  it('names the sub project that will fill an empty slot', () => {
    renderHome();
    const slot = screen.getByTestId('home-slot-spend');
    expect(slot).toHaveTextContent(/not yet collected/i);
    expect(slot).toHaveTextContent(/P1 Cost Intelligence/);
  });

  it('renders no figure and no currency in an empty slot', () => {
    // Rule 5 of 12-UI-DESIGN: an absence is never a number. Asserted as "no
    // Figure and no currency" rather than "no digit", because the slot names
    // the sub project and P1 legitimately contains one.
    renderHome();
    const slot = screen.getByTestId('home-slot-spend');
    expect(slot.querySelector('[data-testid="figure"]')).toBeNull();
    expect(slot).not.toHaveTextContent('$');
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
      '/governance/queries',
    );
    // P1 has not arrived, and its three slots still name it rather than
    // rendering an empty panel.
    expect(screen.getAllByRole('link', { name: /P1 Cost Intelligence/ })).toHaveLength(3);
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
      get: <T,>(path: string) => {
        asked.push(path);
        return inner.get<T>(path);
      },
    };
    renderHome(recording);
    await screen.findByText('$431.00');
    // Both paths belong to a screen that already requests them, through that
    // screen's own hook and its own query key: `usePlatformCost` for the first
    // and `useQueryFindings` for the second. The rule is that Home has no query
    // of its own, not that it makes one request.
    expect([...asked].sort()).toEqual(['/api/v1/platform/cost', '/api/v1/query/findings']);
  });

  it('has no accessibility violations', async () => {
    const { container } = renderHome();
    await screen.findByText('$431.00');
    expect(await violationsIn(container)).toEqual([]);
  });
});
