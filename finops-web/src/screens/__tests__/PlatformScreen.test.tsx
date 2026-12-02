import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { PlatformScreen } from '../PlatformScreen';
import { rollUp } from '../platformRollUp';
import type { PlatformCost } from '../../api/types';
import { clientReturning, metaOf } from './fixtures';
import { Harness } from './Harness';

function cost(day: string, module: string, amount: string): PlatformCost {
  return {
    day,
    module,
    service: 'AmazonECS',
    amortized_cost: amount,
    as_of: `${day}T06:00:00Z`,
    collected_at: `${day}T06:30:00Z`,
  };
}

const ROWS: PlatformCost[] = [
  cost('2026-08-25', 'ingest', '1.00'),
  cost('2026-08-26', 'ingest', '1.50'),
  cost('2026-08-26', 'unallocated', '0.20'),
];

describe('rollUp', () => {
  it('sums a module across days', () => {
    expect(rollUp(ROWS)[0]).toMatchObject({ module: 'ingest', total: 2.5 });
  });

  it('takes the oldest timestamp, because a module is only as fresh as its stalest day', () => {
    expect(rollUp(ROWS)[0]?.asOf).toBe('2026-08-25T06:00:00Z');
  });

  it('orders by spend, so the expensive module is first', () => {
    expect(rollUp(ROWS).map((row) => row.module)).toEqual(['ingest', 'unallocated']);
  });
});

describe('PlatformScreen', () => {
  it('shows spend by module with a thirty day shape', async () => {
    render(
      <Harness
        client={clientReturning({ '/api/v1/platform/cost': { data: ROWS, meta: metaOf() } })}
      >
        <PlatformScreen />
      </Harness>,
    );
    await waitFor(() => {
      expect(screen.getByText('ingest')).toBeInTheDocument();
    });
    expect(screen.getAllByTestId('sparkline').length).toBeGreaterThan(0);
  });

  it('shows the unallocated bucket rather than hiding it', async () => {
    // Hiding it would make the report tidier and wrong, and a self metering
    // report that under counts is worse than none because it is believed.
    render(
      <Harness
        client={clientReturning({ '/api/v1/platform/cost': { data: ROWS, meta: metaOf() } })}
      >
        <PlatformScreen />
      </Harness>,
    );
    await waitFor(() => {
      expect(screen.getByText('unallocated')).toBeInTheDocument();
    });
  });
});
