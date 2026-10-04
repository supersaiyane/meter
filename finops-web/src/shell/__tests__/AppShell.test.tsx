import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { describe, expect, it } from 'vitest';

import { violationsIn } from '../../components/__tests__/axe';
import type { ApiMeta } from '../../api/types';
import { AppShell } from '../AppShell';
import { allScreens } from '../sections';
import { MetaProvider } from '../MetaProvider';
import { useReportMeta } from '../metaRegistry';
import type { FreshnessSource } from '../metaStore';

const NOW = new Date('2026-08-27T10:00:00Z');

function metaOf(partial: Partial<ApiMeta> = {}): ApiMeta {
  return {
    as_of: '2026-08-27T09:00:00Z',
    collected_at: '2026-08-27T09:54:00Z',
    scope_coverage: { visible: 5, total: 5, is_partial: false, unit: 'accounts' },
    degraded: false,
    failures: [],
    ...partial,
  };
}

/** A surface that reports one meta, as a real screen will. */
function Surface({ meta }: { readonly meta: ApiMeta }) {
  useReportMeta('surface', meta);
  return <p>rows</p>;
}

function renderShell(meta?: ApiMeta, initialPath = '/inventory/accounts') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <MetaProvider>
        <AppShell now={NOW}>{meta ? <Surface meta={meta} /> : <p>rows</p>}</AppShell>
      </MetaProvider>
    </MemoryRouter>,
  );
}

interface Reported {
  readonly id: string;
  readonly meta: ApiMeta;
  readonly freshness: FreshnessSource;
}

/** One surface that reports where its figures say how fresh they are, as a P7 screen will. */
function Reporting({ id, meta, freshness }: Reported) {
  useReportMeta(id, meta, freshness);
  return null;
}

function renderShellWith(surfaces: readonly Reported[]) {
  return render(
    <MemoryRouter initialEntries={['/assistant']}>
      <MetaProvider>
        <AppShell now={NOW}>
          {surfaces.map((surface) => (
            <Reporting key={surface.id} {...surface} />
          ))}
        </AppShell>
      </MetaProvider>
    </MemoryRouter>,
  );
}

describe('AppShell', () => {
  it('reads showing N of M accounts whenever coverage is partial', () => {
    renderShell(
      metaOf({
        scope_coverage: { visible: 42, total: 310, is_partial: true, unit: 'accounts' },
      }),
    );
    expect(screen.getByText('Showing 42 of 310 accounts')).toBeInTheDocument();
  });

  it('confirms complete coverage rather than going quiet', () => {
    // The absence of a warning is not confirmation, and a reader needs
    // confirmation before treating a total as a total.
    renderShell(
      metaOf({
        scope_coverage: { visible: 310, total: 310, is_partial: false, unit: 'accounts' },
      }),
    );
    expect(screen.getByText('Showing all 310 accounts')).toBeInTheDocument();
  });

  it('gives no way to dismiss the coverage banner', () => {
    // A banner gets dismissed. The condition does not go away with it.
    renderShell(
      metaOf({ scope_coverage: { visible: 1, total: 2, is_partial: true, unit: 'accounts' } }),
    );
    const banner = screen.getByTestId('coverage');
    expect(banner.querySelector('button')).toBeNull();
  });

  it('shows the oldest as_of in view', () => {
    renderShell(metaOf({ as_of: '2026-08-27T04:00:00Z' }));
    expect(screen.getByTestId('global-freshness').textContent).toContain(
      'as of 2026-08-27 04:00',
    );
  });

  it('says not yet collected rather than showing an empty success', () => {
    renderShell(metaOf({ as_of: null, collected_at: null }));
    expect(screen.getByTestId('global-freshness').dataset['state']).toBe('never-collected');
    expect(screen.getByText('Not yet collected')).toBeInTheDocument();
  });

  it('says freshness is beside each figure when every surface says its figures carry their own', () => {
    // The assistant's case: the envelopes hold Meter's own work and no as_of, and every cited
    // figure carries the as_of of its row. Not yet collected would be false, and a date for
    // the page would be made up.
    renderShellWith([
      {
        id: 'exchanges',
        meta: metaOf({ as_of: null, collected_at: null }),
        freshness: 'per-figure',
      },
      {
        id: 'redactions',
        meta: metaOf({ as_of: null, collected_at: null }),
        freshness: 'per-figure',
      },
    ]);
    const freshness = screen.getByTestId('global-freshness');
    expect(freshness.dataset['state']).toBe('per-figure');
    expect(freshness).toHaveTextContent('Each citation carries its own as of date');
    expect(screen.queryByText('Not yet collected')).toBeNull();
  });

  it('keeps not yet collected for an envelope with none, even beside a per figure surface', () => {
    // The envelope's claim is true of it, so the strip keeps saying it.
    renderShellWith([
      {
        id: 'exchanges',
        meta: metaOf({ as_of: null, collected_at: null }),
        freshness: 'per-figure',
      },
      { id: 'cost', meta: metaOf({ as_of: null, collected_at: null }), freshness: 'envelope' },
    ]);
    expect(screen.getByTestId('global-freshness').dataset['state']).toBe('never-collected');
    expect(screen.getByText('Not yet collected')).toBeInTheDocument();
  });

  it('keeps the oldest in view for an envelope with one, beside a per figure surface', () => {
    renderShellWith([
      {
        id: 'exchanges',
        meta: metaOf({ as_of: null, collected_at: null }),
        freshness: 'per-figure',
      },
      { id: 'cost', meta: metaOf({ as_of: '2026-08-27T04:00:00Z' }), freshness: 'envelope' },
    ]);
    const freshness = screen.getByTestId('global-freshness');
    expect(freshness.dataset['state']).toBe('collected');
    expect(freshness).toHaveTextContent('as of 2026-08-27 04:00');
  });

  it('makes a degraded response visually distinct from a healthy one', () => {
    const healthy = renderShell(metaOf());
    expect(healthy.getByTestId('shell').dataset['degraded']).toBe('false');
    healthy.unmount();

    const degraded = renderShell(
      metaOf({
        degraded: true,
        failures: [
          {
            scope_key: 'aws:111122223333:eu-west-1',
            collector: 'account_health',
            cause: 'AccessDenied',
            remediation: 'Check the StackSet deployment.',
            occurrences: 2,
            last_seen_at: '2026-08-27T09:00:00Z',
          },
        ],
      }),
    );
    expect(degraded.getByTestId('shell').dataset['degraded']).toBe('true');
  });

  it('names which collector is failing rather than showing a generic error', () => {
    renderShell(
      metaOf({
        degraded: true,
        failures: [
          {
            scope_key: 'aws:111122223333:eu-west-1',
            collector: 'account_health',
            cause: 'AccessDenied',
            remediation: 'Check the StackSet deployment.',
            occurrences: 2,
            last_seen_at: '2026-08-27T09:00:00Z',
          },
        ],
      }),
    );
    expect(screen.getByText('ACCESS DENIED')).toBeInTheDocument();
    expect(screen.getByText(/account_health on aws:111122223333/)).toBeInTheDocument();
  });

  it('still shows a cause the frontend does not recognise', () => {
    // Hiding it because the vocabulary drifted would hide the drift.
    renderShell(
      metaOf({
        degraded: true,
        failures: [
          {
            scope_key: 'aws:1:eu-west-1',
            collector: 'org_tree',
            cause: 'SomethingNew',
            remediation: 'Read the detail.',
            occurrences: 1,
            last_seen_at: '2026-08-27T09:00:00Z',
          },
        ],
      }),
    );
    expect(screen.getByText(/SomethingNew on aws:1/)).toBeInTheDocument();
  });

  it('withdraws a surface meta when the surface leaves', () => {
    const view = renderShell(
      metaOf({ scope_coverage: { visible: 2, total: 9, is_partial: true, unit: 'accounts' } }),
    );
    expect(screen.getByText('Showing 2 of 9 accounts')).toBeInTheDocument();
    view.rerender(
      <MemoryRouter initialEntries={['/inventory/accounts']}>
        <MetaProvider>
          <AppShell now={NOW}>
            <p>rows</p>
          </AppShell>
        </MetaProvider>
      </MemoryRouter>,
    );
    expect(screen.queryByText('Showing 2 of 9 accounts')).toBeNull();
  });

  it('marks the current screen for assistive technology', () => {
    renderShell(metaOf());
    expect(screen.getByRole('link', { name: 'Accounts' })).toHaveAttribute(
      'aria-current',
      'page',
    );
  });

  it('lists an unbuilt screen with what will fill it, rather than hiding it', () => {
    // Derived rather than named, for the same reason as the sections test: a
    // journey pinned to one path stops testing the mechanism the day that path
    // ships, and this one failed twice that way before it was fixed properly.
    renderShell(metaOf());
    const unbuilt = allScreens().find((s) => s.arrives !== null);
    expect(unbuilt).toBeDefined();
    const link = document.querySelector(`a[href="${unbuilt?.path ?? ''}"]`);
    expect(link).toHaveAttribute('data-arrives', unbuilt?.arrives ?? '');
  });

  it('gives a built screen no arrival note', () => {
    renderShell(metaOf());
    const link = screen.getByRole('link', { name: /Spend and trend/ });
    expect(link).not.toHaveAttribute('data-arrives');
  });

  it('reports no accessibility violations when degraded', async () => {
    const { container } = renderShell(
      metaOf({
        degraded: true,
        scope_coverage: { visible: 1, total: 4, is_partial: true, unit: 'accounts' },
        failures: [
          {
            scope_key: 'aws:1:eu-west-1',
            collector: 'org_tree',
            cause: 'Throttled',
            remediation: 'Retrying shortly.',
            occurrences: 1,
            last_seen_at: '2026-08-27T09:00:00Z',
          },
        ],
      }),
    );
    expect(await violationsIn(container)).toEqual([]);
  });
});
