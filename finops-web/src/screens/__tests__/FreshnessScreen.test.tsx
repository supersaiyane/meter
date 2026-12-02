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
    is_stale: false,
  },
  {
    collector: 'account_health',
    scope_key: 'aws:1:eu-west-1',
    as_of: '2026-08-27T01:00:00Z',
    cadence_seconds: 3600,
    age_seconds: 32400,
    is_stale: true,
  },
  {
    collector: 'unscheduled',
    scope_key: 'organization',
    as_of: '2026-08-27T09:55:00Z',
    cadence_seconds: null,
    age_seconds: 300,
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
      expect(screen.getByText('org_tree')).toBeInTheDocument();
    });
    expect(screen.getAllByText('stale')).toHaveLength(2);
    expect(screen.getByText('current')).toBeInTheDocument();
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
      expect(screen.getAllByText('60 min')).toHaveLength(2);
    });
    expect(screen.getByText('not scheduled')).toBeInTheDocument();
  });
});
