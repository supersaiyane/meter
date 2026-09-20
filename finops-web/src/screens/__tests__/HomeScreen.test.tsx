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
    // Derived, not named. This asserted on `home-slot-spend` until 2026-09-20, when
    // P1 filled that slot and the test failed for the one reason that is not a
    // regression. The claim is about the mechanism, so it is made against whichever
    // slot is empty today.
    renderHome();
    const slots = screen.getAllByTestId(/^home-slot-/);
    expect(slots.length).toBeGreaterThan(0);
    for (const slot of slots) {
      expect(slot).toHaveTextContent(/not yet collected/i);
      expect(slot).toHaveTextContent(/^.*P\d /);
    }
  });

  it('renders no figure and no currency in an empty slot', () => {
    // Rule 5 of 12-UI-DESIGN: an absence is never a number. Asserted as "no Figure
    // and no currency" rather than "no digit", because the slot names the sub project
    // and P3 legitimately contains one.
    renderHome();
    for (const slot of screen.getAllByTestId(/^home-slot-/)) {
      expect(slot.querySelector('[data-testid="figure"]')).toBeNull();
      expect(slot).not.toHaveTextContent('$');
    }
  });

  it('shows the spend P1 filled rather than still promising it', () => {
    // The defect this replaces was on the front page of a demo: three slots saying
    // total spend and trend arrive with P1, on a build where /cost shows both. A
    // product that does not know what it has is worse than one that never mentioned
    // the feature.
    renderHome();
    expect(screen.queryByText(/P1 Cost Intelligence/)).toBeNull();
    expect(screen.getByRole('link', { name: /Total spend/ })).toHaveAttribute('href', '/cost');
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
    // Every remaining slot links to the screen that will own it, rather than
    // rendering an empty panel. Counted rather than named, for the reason above.
    const slots = screen.getAllByTestId(/^home-slot-/);
    for (const slot of slots) {
      expect(slot.querySelector('a')).not.toBeNull();
    }
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
      getText: (path: string) => inner.getText(path),
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
      // `useCostSummary`, which is the spend screen's own hook. Home shows the total
      // and the change; it computes neither.
      '/api/v1/cost/summary',
      '/api/v1/platform/cost',
      '/api/v1/query/findings',
      '/api/v1/query/groups',
      '/api/v1/query/instances',
    ]);
  });

  it('has no accessibility violations', async () => {
    const { container } = renderHome();
    await screen.findByText('$431.00');
    expect(await violationsIn(container)).toEqual([]);
  });
});
