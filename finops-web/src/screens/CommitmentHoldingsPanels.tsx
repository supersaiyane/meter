import { useId, useMemo } from 'react';

import { useCommitmentCalendar, useCommitmentInventory } from '../api/queries';
import type { ApiCalendarMonth, ApiHeldCommitment } from '../api/types';
import { DataTable } from '../components/DataTable';
import { Figure } from '../components/Figure';
import { FreshnessIndicator } from '../components/FreshnessIndicator';
import { PercentCell } from '../components/PercentCell';
import { StateBoundary } from '../components/StateBoundary';
import type { Column } from '../components/tableConfig';
import { useReportMeta } from '../shell/metaRegistry';
import { dayName, freshnessOf, monthName } from './commitmentFormat';
import { surfaceStateFor } from './surfaceStateFor';

/**
 * What the payer holds and when it ends. FEAT-086 and FEAT-088, TASK-P14-009.
 *
 * Both are the payer's, ADR-0025, read only for a reader whose scope is the whole organization; the
 * screen says why to anyone else. A Savings Plan states an amount an hour, measured. A reservation
 * buys instances, so its hourly value is modelled, and a figure says which it is.
 */

function kindName(row: ApiHeldCommitment): string {
  return row.kind === 'savings_plan'
    ? `${row.program} Savings Plan`
    : `${row.program} reservation`;
}

function heldColumns(
  freshness: ReturnType<typeof freshnessOf>,
): readonly Column<ApiHeldCommitment>[] {
  return [
    {
      key: 'commitment',
      header: 'Commitment',
      rowHeader: true,
      render: (row) => row.commitment_id,
      sortValue: (row) => row.commitment_id,
    },
    { key: 'kind', header: 'Kind', render: kindName, sortValue: kindName },
    { key: 'account', header: 'Account', render: (row) => row.account_id },
    {
      key: 'covers',
      header: 'Covers',
      render: (row) => row.applies_to ?? 'any eligible usage',
    },
    {
      key: 'amount',
      header: 'Amount',
      numeric: true,
      // Exactly one of the two, as the database holds it.
      render: (row) =>
        row.hourly_commitment === null ? (
          `${String(row.quantity ?? 0)} instances`
        ) : (
          <>
            <Figure
              value={{ kind: 'measured', amount: Number(row.hourly_commitment) }}
              freshness={freshness}
              unit="usd-unit"
            />{' '}
            an hour
          </>
        ),
    },
    {
      key: 'term',
      header: 'Term and payment',
      render: (row) => `${String(row.term_months)} months, ${row.payment_option}`,
    },
    {
      key: 'ends',
      header: 'Ends',
      render: (row) => dayName(row.ends_at),
      sortValue: (row) => row.ends_at,
    },
    { key: 'state', header: 'State', render: (row) => row.state },
  ];
}

export function InventoryPanel() {
  const heading = useId();
  const query = useCommitmentInventory(true);
  const envelope = query.data;
  const held = useMemo(() => envelope?.data.commitments ?? [], [envelope]);
  const unreadable = envelope?.data.unreadable ?? [];
  useReportMeta('commitment-inventory', envelope?.meta);
  const state = surfaceStateFor(
    query,
    envelope?.meta,
    held.length,
    'none',
    'commitment_inventory',
  );
  const freshness = freshnessOf(envelope?.meta);
  return (
    <section
      className="meter-panel"
      aria-labelledby={heading}
      data-testid="commitment-inventory"
    >
      <h2 id={heading}>Commitments held</h2>
      <p>
        Every Savings Plan and reservation, with its real term and end, the soonest ending
        first. Measured, from the service that sold it
        {envelope?.meta.as_of ? <FreshnessIndicator freshness={freshness} /> : null}
      </p>
      {unreadable.length > 0 ? (
        <p data-testid="commitment-unreadable">
          {unreadable.join(' and ')} reserved capacity has no API to read, so it is not listed
          here. That is not the same as none held.
        </p>
      ) : null}
      <StateBoundary state={state}>
        <DataTable
          rows={held}
          columns={heldColumns(freshness)}
          rowKey={(row) => `${row.kind}:${row.commitment_id}`}
          caption={`${String(held.length)} commitments, the soonest ending first`}
        />
      </StateBoundary>
    </section>
  );
}

function percentText(fraction: string): string {
  return `${(Number(fraction) * 100).toFixed(2).replace(/\.?0+$/, '')} percent`;
}

function calendarColumns(
  freshness: ReturnType<typeof freshnessOf>,
  limit: string,
): readonly Column<ApiCalendarMonth>[] {
  return [
    {
      key: 'month',
      header: 'Month',
      rowHeader: true,
      render: (row) => monthName(row.month),
      sortValue: (row) => row.month,
    },
    {
      key: 'ending',
      header: 'Ending',
      prose: true,
      render: (row) =>
        row.commitments.length === 0 ? 'Nothing ends' : row.commitments.join(', '),
    },
    {
      key: 'value',
      header: 'Hourly commitment ending',
      numeric: true,
      render: (row) => (
        <Figure
          value={{ kind: row.basis, amount: Number(row.hourly_value) }}
          freshness={freshness}
          unit="usd-unit"
        />
      ),
    },
    {
      key: 'share',
      header: 'Share of all held',
      numeric: true,
      render: (row) => (
        <PercentCell
          fraction={row.share === null ? null : Number(row.share)}
          absent="nothing held"
          provenance={row.basis}
        />
      ),
    },
    {
      key: 'ladder',
      header: 'Against the ladder',
      render: (row) =>
        row.over_limit ? (
          <strong data-testid={`over-limit-${row.month}`}>
            Above the {percentText(limit)} limit
          </strong>
        ) : (
          'Within the limit'
        ),
    },
  ];
}

export function CalendarPanel() {
  const heading = useId();
  const query = useCommitmentCalendar(true);
  const envelope = query.data;
  const months = useMemo(() => envelope?.data.months ?? [], [envelope]);
  useReportMeta('commitment-calendar', envelope?.meta);
  const state = surfaceStateFor(
    query,
    envelope?.meta,
    months.length,
    'none',
    'commitment_inventory',
  );
  const freshness = freshnessOf(envelope?.meta);
  const limit = envelope?.data.ladder_limit ?? '0';
  return (
    <section
      className="meter-panel"
      aria-labelledby={heading}
      data-testid="commitment-calendar"
    >
      <h2 id={heading}>When commitments end</h2>
      <p>
        The next twelve months: what ends in each, and its share of the hourly commitment held.
        At most {percentText(limit)} should end in any one month, the policy&apos;s ladder
        {envelope?.meta.as_of ? <FreshnessIndicator freshness={freshness} /> : null}
      </p>
      <StateBoundary state={state}>
        <DataTable
          rows={months}
          columns={calendarColumns(freshness, limit)}
          rowKey={(row) => row.month}
          caption="Twelve months, the soonest first"
        />
      </StateBoundary>
    </section>
  );
}
