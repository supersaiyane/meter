import { render, screen, within, waitFor } from '@testing-library/react';
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
      expect(within(screen.getByRole('table')).getByText('ingest')).toBeInTheDocument();
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
      expect(within(screen.getByRole('table')).getByText('unallocated')).toBeInTheDocument();
    });
  });

  it('states what Meter costs to run rather than leaving the rows to add up', async () => {
    // Constraint 7: the platform meters itself and its own cost is on the front page. It was on
    // the front page and not on its own screen, so the one place that exists to answer this
    // question made a reader sum the table. The fixture is 1.00 and 1.50 of ingest plus 0.20
    // unallocated.
    render(
      <Harness
        client={clientReturning({ '/api/v1/platform/cost': { data: ROWS, meta: metaOf() } })}
      >
        <PlatformScreen />
      </Harness>,
    );
    const figure = await screen.findByTestId('platform-total-figure');
    expect(figure).toHaveTextContent('$2.70');
  });

  it('dates the total by its stalest day, not its freshest', async () => {
    // A total is only as fresh as the oldest thing in it, and `grandTotal` takes the minimum for
    // that reason. Reporting the newest would make a total containing a stale module look like
    // it was read this morning. The fixture's oldest day is the 25th and its newest is the 26th.
    render(
      <Harness
        client={clientReturning({ '/api/v1/platform/cost': { data: ROWS, meta: metaOf() } })}
      >
        <PlatformScreen />
      </Harness>,
    );
    const figure = await screen.findByTestId('platform-total-figure');
    expect(figure).toHaveTextContent('2026-08-25');
    expect(figure).not.toHaveTextContent('2026-08-26');
  });
});
