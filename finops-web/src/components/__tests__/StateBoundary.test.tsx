import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { StateBoundary } from '../StateBoundary';
import { SURFACE_STATES, type SurfaceState } from '../surfaceState';
import { violationsIn } from './axe';

/** One example of every state, so the list and the boundary cannot drift apart. */
const EXAMPLES: Record<(typeof SURFACE_STATES)[number], SurfaceState> = {
  loading: { kind: 'loading', rows: 3 },
  empty: { kind: 'empty', filter: 'role health is healthy' },
  'never-collected': { kind: 'never-collected', collector: 'org_tree', nextRun: 'in 40 min' },
  partial: { kind: 'partial', missing: 3, reason: 'three accounts could not be read' },
  stale: { kind: 'stale', age: '9 h' },
  degraded: { kind: 'degraded', failing: ['account_health'] },
  failed: { kind: 'failed', cause: 'AccessDenied', remediation: 'Check the StackSet.' },
};

describe('StateBoundary', () => {
  it('implements_seven_states', () => {
    // Not three. A surface that implements five is not finished, so the count is
    // asserted rather than trusted to review.
    expect(SURFACE_STATES).toHaveLength(7);
    for (const kind of SURFACE_STATES) {
      const { unmount } = render(
        <StateBoundary state={EXAMPLES[kind]}>
          <p>rows</p>
        </StateBoundary>,
      );
      expect(screen.getByTestId('state').dataset['state']).toBe(kind);
      unmount();
    }
  });

  it('keeps showing the rows for the three states that still have data', () => {
    // Partial, stale and degraded add something beside the data. Hiding the rows
    // would be a different lie from the one being prevented.
    for (const kind of ['partial', 'stale', 'degraded'] as const) {
      const { unmount } = render(
        <StateBoundary state={EXAMPLES[kind]}>
          <p>rows</p>
        </StateBoundary>,
      );
      expect(screen.getByText('rows')).toBeInTheDocument();
      unmount();
    }
  });

  it('states the coverage claim by default', () => {
    render(
      <StateBoundary state={EXAMPLES.partial}>
        <p>rows</p>
      </StateBoundary>,
    );
    expect(screen.getByRole('status')).toHaveTextContent('3 missing');
  });

  it('drops the sentence, never the rows, when coverage is claimed elsewhere', () => {
    // Four tiles summarising one partially read estate repeat an identical
    // sentence four times and announce it four times, which buries the claim.
    // The opt out must never take the data with it.
    render(
      <StateBoundary state={EXAMPLES.partial} coverageShownElsewhere>
        <p>rows</p>
      </StateBoundary>,
    );
    expect(screen.queryByRole('status')).toBeNull();
    expect(screen.getByText('rows')).toBeInTheDocument();
    expect(screen.getByTestId('state').dataset['state']).toBe('partial');
  });

  it('renders a skeleton at the final dimensions rather than a spinner', () => {
    render(
      <StateBoundary state={{ kind: 'loading', rows: 4 }}>
        <p>rows</p>
      </StateBoundary>,
    );
    // A spinner hides how much is coming. Four rows are coming, so four appear.
    expect(screen.getAllByTestId('skeleton-row')).toHaveLength(4);
  });

  it('does not let a genuine empty look like a failure', () => {
    render(
      <StateBoundary state={{ kind: 'empty', filter: 'suspended only' }}>
        <p>rows</p>
      </StateBoundary>,
    );
    expect(screen.getByText(/Nothing matches this filter/)).toBeInTheDocument();
    expect(screen.getByText(/suspended only/)).toBeInTheDocument();
  });

  it('does not let never collected render as an empty success', () => {
    render(
      <StateBoundary state={EXAMPLES['never-collected']}>
        <p>rows</p>
      </StateBoundary>,
    );
    expect(screen.getByText(/Not yet collected by Organization/)).toBeInTheDocument();
    expect(screen.getByText(/Next run in 40 min/)).toBeInTheDocument();
  });

  it('renders no numeral in the failed state', () => {
    const { container } = render(
      <StateBoundary state={EXAMPLES.failed}>
        <p>rows</p>
      </StateBoundary>,
    );
    expect(container.querySelector('.meter-numeral')).toBeNull();
    expect(screen.getByText('ACCESS DENIED')).toBeInTheDocument();
  });

  it('names the failing collectors in words, never by their codes', () => {
    render(
      <StateBoundary state={{ kind: 'degraded', failing: ['account_health', 'finops_score'] }}>
        <p>rows</p>
      </StateBoundary>,
    );
    const said = screen.getByRole('status');
    expect(said).toHaveTextContent('Failing: Account health, FinOps Score.');
    expect(said.textContent).not.toMatch(/account_health|finops_score/);
  });

  it('reports no accessibility violations in any state', async () => {
    for (const kind of SURFACE_STATES) {
      const { container, unmount } = render(
        <StateBoundary state={EXAMPLES[kind]}>
          <p>rows</p>
        </StateBoundary>,
      );
      expect(await violationsIn(container)).toEqual([]);
      unmount();
    }
  });
});
