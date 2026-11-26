import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { violationsIn } from '../../components/__tests__/axe';
import type { ApiMeta } from '../../api/types';
import { AppShell } from '../AppShell';
import { MetaProvider } from '../MetaProvider';
import { useReportMeta } from '../metaRegistry';

const NOW = new Date('2026-08-27T10:00:00Z');

function metaOf(partial: Partial<ApiMeta> = {}): ApiMeta {
  return {
    as_of: '2026-08-27T09:00:00Z',
    collected_at: '2026-08-27T09:54:00Z',
    scope_coverage: { visible: 5, total: 5, is_partial: false },
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

function renderShell(meta?: ApiMeta) {
  return render(
    <MetaProvider>
      <AppShell section="Accounts" onSelect={() => undefined} now={NOW}>
        {meta ? <Surface meta={meta} /> : <p>rows</p>}
      </AppShell>
    </MetaProvider>,
  );
}

describe('AppShell', () => {
  it('reads showing N of M accounts whenever coverage is partial', () => {
    renderShell(metaOf({ scope_coverage: { visible: 42, total: 310, is_partial: true } }));
    expect(screen.getByText('Showing 42 of 310 accounts')).toBeInTheDocument();
  });

  it('confirms complete coverage rather than going quiet', () => {
    // The absence of a warning is not confirmation, and a reader needs
    // confirmation before treating a total as a total.
    renderShell(metaOf({ scope_coverage: { visible: 310, total: 310, is_partial: false } }));
    expect(screen.getByText('Showing all 310 accounts')).toBeInTheDocument();
  });

  it('gives no way to dismiss the coverage banner', () => {
    // A banner gets dismissed. The condition does not go away with it.
    renderShell(metaOf({ scope_coverage: { visible: 1, total: 2, is_partial: true } }));
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
      metaOf({ scope_coverage: { visible: 2, total: 9, is_partial: true } }),
    );
    expect(screen.getByText('Showing 2 of 9 accounts')).toBeInTheDocument();
    view.rerender(
      <MetaProvider>
        <AppShell section="Accounts" onSelect={() => undefined} now={NOW}>
          <p>rows</p>
        </AppShell>
      </MetaProvider>,
    );
    expect(screen.queryByText('Showing 2 of 9 accounts')).toBeNull();
  });

  it('marks the current section for assistive technology', () => {
    renderShell(metaOf());
    expect(screen.getByRole('button', { name: 'Accounts' })).toHaveAttribute(
      'aria-current',
      'page',
    );
  });

  it('reports no accessibility violations when degraded', async () => {
    const { container } = renderShell(
      metaOf({
        degraded: true,
        scope_coverage: { visible: 1, total: 4, is_partial: true },
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
