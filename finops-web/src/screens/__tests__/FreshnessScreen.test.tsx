import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { FreshnessScreen } from '../FreshnessScreen';
import type { Freshness } from '../../api/types';
import { clientReturning, metaOf } from './fixtures';
import { Harness } from './Harness';

const ROWS: Freshness[] = [
  {
    collector: 'org_tree',
    scope_key: 'organization',
    as_of: '2026-08-27T09:55:00Z',
    cadence_seconds: 3600,
    age_seconds: 300,
    state: 'current',
    cause: null,
    is_stale: false,
  },
  {
    collector: 'account_health',
    scope_key: 'aws:1:eu-west-1',
    as_of: '2026-08-27T01:00:00Z',
    cadence_seconds: 3600,
    age_seconds: 32400,
    state: 'stale',
    cause: null,
    is_stale: true,
  },
  {
    collector: 'unscheduled',
    scope_key: 'organization',
    as_of: '2026-08-27T09:55:00Z',
    cadence_seconds: null,
    age_seconds: 300,
    state: 'stale',
    cause: null,
    is_stale: true,
  },
  {
    // The row this page exists for and did not have. ISS-163.
    collector: 'account_health',
    scope_key: 'aws:2:eu-west-1',
    as_of: null,
    cadence_seconds: 3600,
    age_seconds: null,
    state: 'never_collected',
    cause: 'AccessDenied',
    is_stale: true,
  },
];

describe('FreshnessScreen', () => {
  it('reports staleness per collector and per scope', async () => {
    render(
      <Harness
        client={clientReturning({ '/api/v1/health/freshness': { data: ROWS, meta: metaOf() } })}
      >
        <FreshnessScreen />
      </Harness>,
    );
    await waitFor(() => {
      expect(screen.getByText('Organization')).toBeInTheDocument();
    });
    expect(screen.getAllByText('stale')).toHaveLength(2);
    expect(screen.getByText('current')).toBeInTheDocument();
  });

  it('lists a collector that has never succeeded, with its cause', async () => {
    // The row a reader comes to this page to find, and the one it left out: the
    // page listed watermarks, and a watermark only exists after a success.
    // ISS-163.
    render(
      <Harness
        client={clientReturning({ '/api/v1/health/freshness': { data: ROWS, meta: metaOf() } })}
      >
        <FreshnessScreen />
      </Harness>,
    );
    await waitFor(() => {
      expect(screen.getByText(/never collected, AccessDenied/)).toBeInTheDocument();
    });
  });

  it('renders an absent age as never rather than as a zero', async () => {
    // A zero would read as collected this instant, which is the opposite of
    // what is true.
    render(
      <Harness
        client={clientReturning({ '/api/v1/health/freshness': { data: ROWS, meta: metaOf() } })}
      >
        <FreshnessScreen />
      </Harness>,
    );
    await waitFor(() => {
      expect(screen.getByText('never')).toBeInTheDocument();
    });
    expect(screen.queryByText('under a minute ago')).toBeNull();
  });

  it('shows the cadence beside the age, because one threshold cannot fit both', async () => {
    // A daily collector six hours old is fine and an hourly one six hours old
    // is not, so the reader is given the number the judgement used.
    render(
      <Harness
        client={clientReturning({ '/api/v1/health/freshness': { data: ROWS, meta: metaOf() } })}
      >
        <FreshnessScreen />
      </Harness>,
    );
    await waitFor(() => {
      expect(screen.getAllByText('60 min')).toHaveLength(3);
    });
    expect(screen.getByText('not scheduled')).toBeInTheDocument();
  });

  it('counts the collectors past their own cadence, and only those', async () => {
    // The question somebody opens this screen with, answered rather than left as four rows to
    // read. The fixture has two collectors that can be judged and one of them is nine times its
    // cadence, so the count is one of two and never one of four.
    render(
      <Harness
        client={clientReturning({ '/api/v1/health/freshness': { data: ROWS, meta: metaOf() } })}
      >
        <FreshnessScreen />
      </Harness>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('freshness-summary')).toHaveTextContent(
        '1 of 2 collectors are past their own cadence',
      );
    });
  });

  it('leaves what cannot be judged out of both halves of that count', async () => {
    // The failure the count makes easy. A collector nothing schedules cannot be late, and one
    // that never succeeded has no age at all. Rolling either into the numerator inflates the
    // number that decides whether somebody investigates, and rolling them into the denominator
    // deflates it. Both are named separately instead.
    render(
      <Harness
        client={clientReturning({ '/api/v1/health/freshness': { data: ROWS, meta: metaOf() } })}
      >
        <FreshnessScreen />
      </Harness>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('freshness-summary')).toHaveTextContent(
        '2 more cannot be judged at all, and are counted as neither late nor current',
      );
    });
  });

  it('agrees in number when exactly one collector cannot be judged', async () => {
    // Found by looking at the seeded estate, where exactly one collector is unschedulable and
    // the sentence read "1 more cannot be judged at all, and are". The fixture has two of them,
    // so every assertion above exercised only the plural.
    const one = ROWS.filter((row) => row.collector !== 'unscheduled');
    render(
      <Harness
        client={clientReturning({ '/api/v1/health/freshness': { data: one, meta: metaOf() } })}
      >
        <FreshnessScreen />
      </Harness>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('freshness-summary')).toHaveTextContent(
        '1 more cannot be judged at all, and is counted as neither late nor current',
      );
    });
  });

  it('draws each row against its own cadence rather than a shared threshold', async () => {
    // Two collectors, both an hour of cadence, one at nine times and one at a twelfth. The
    // screen has to show that difference as a difference, which the age column alone does not:
    // 32400 seconds beside 300 is arithmetic a reader should not have to do.
    render(
      <Harness
        client={clientReturning({ '/api/v1/health/freshness': { data: ROWS, meta: metaOf() } })}
      >
        <FreshnessScreen />
      </Harness>,
    );
    const bars = await screen.findAllByTestId('cadence');
    expect(bars).toHaveLength(2);
    const states = bars.map((one) => one.getAttribute('data-state'));
    expect(states).toEqual(['due', 'over']);
  });

  it('says why a row has no bar rather than leaving the cell blank', async () => {
    // A blank cell reads as a rendering fault and sends somebody looking for a value that was
    // never there. Two rows here have no lateness and they have different reasons.
    render(
      <Harness
        client={clientReturning({ '/api/v1/health/freshness': { data: ROWS, meta: metaOf() } })}
      >
        <FreshnessScreen />
      </Harness>,
    );
    const absent = await screen.findAllByTestId('cadence-absent');
    expect(absent).toHaveLength(2);
    expect(absent.map((one) => one.textContent)).toEqual([
      'nothing schedules this, so it cannot be late',
      'never collected, so there is no age',
    ]);
  });
});
