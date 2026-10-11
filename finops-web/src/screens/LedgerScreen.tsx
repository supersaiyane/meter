import { useMemo, useState } from 'react';

import { useLedger, useLedgerCredits } from '../api/queries';
import type { ApiLedgerCredit, ApiLedgerMonth, ApiLedgerTeam } from '../api/types';
import { DataTable } from '../components/DataTable';
import { monthStateName } from '../components/displayNames';
import { Figure } from '../components/Figure';
import { StateBoundary } from '../components/StateBoundary';
import type { Column } from '../components/tableConfig';
import { useReportMeta } from '../shell/metaRegistry';
import { surfaceStateFor } from './surfaceStateFor';

/**
 * The savings ledger. FEAT-078, TASK-P11-008.
 *
 * Teams by the savings they hold: each saving verified against the bill is credited to the team
 * named for its resource, and every closed month since adds what the bill showed it still saving.
 * Measured throughout. A held saving is what the months showed, never a projection, and a month the
 * account's bill holds nothing for says so rather than counting as a zero.
 *
 * **Teams, never people**, OPEN-27. The table ranks teams. A person's name appears only as the
 * owner and closer on one team's own credits, after a reader has chosen that team, and never in a
 * ranking: a leaderboard of named engineers is a performance review nobody asked Meter to run.
 */

const NO_TEAM = 'No team named';

function teamName(team: string | null): string {
  return team ?? NO_TEAM;
}

function monthName(first: string): string {
  return new Date(`${first}T00:00:00Z`).toLocaleString('en-GB', {
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  });
}

/** Each closed month in words, or that none has closed. */
function monthsInWords(months: readonly ApiLedgerMonth[]): string {
  if (months.length === 0) {
    return 'no month closed yet';
  }
  return months
    .map((one) => `${monthName(one.month)}: ${monthStateName(one.state).toLowerCase()}`)
    .join(', ');
}

export function LedgerScreen() {
  const ledger = useLedger();
  const credits = useLedgerCredits();
  const envelope = ledger.data?.data;
  const teams = useMemo(() => envelope?.data.teams ?? [], [envelope]);
  const every = useMemo(() => credits.data?.data.data.credits ?? [], [credits.data]);
  // Undefined until a reader chooses a team; null is the team no source named.
  const [chosen, choose] = useState<string | null | undefined>(undefined);

  useReportMeta('savings-ledger', envelope?.meta);
  const state = surfaceStateFor(ledger, envelope?.meta, teams.length, 'none', 'savings_ledger');
  const freshness = {
    asOf: new Date(envelope?.meta.as_of ?? 0),
    collectedAt: new Date(envelope?.meta.collected_at ?? 0),
  };
  const shown = chosen === undefined ? [] : every.filter((one) => one.team === chosen);

  const teamColumns: readonly Column<ApiLedgerTeam>[] = [
    {
      key: 'team',
      header: 'Team',
      render: (row) => (
        <button
          type="button"
          aria-pressed={chosen === row.team}
          data-testid={`team-${row.team ?? 'none'}`}
          onClick={() => {
            choose(row.team);
          }}
        >
          {teamName(row.team)}
        </button>
      ),
    },
    {
      key: 'held',
      header: 'Saving held',
      numeric: true,
      sortValue: (row) => Number(row.saving_held),
      render: (row) => (
        <Figure
          value={{ kind: 'measured', amount: Number(row.saving_held) }}
          freshness={freshness}
        />
      ),
    },
    {
      key: 'months',
      header: 'Months held',
      numeric: true,
      render: (row) => row.months_held,
    },
    {
      key: 'credits',
      header: 'Verified savings',
      numeric: true,
      render: (row) => row.credits,
    },
    {
      key: 'regressed',
      header: 'Stopped by a regression',
      numeric: true,
      render: (row) => row.regressed,
    },
    {
      key: 'latest',
      header: 'Latest month',
      render: (row) =>
        row.latest_month === null ? 'none closed yet' : monthName(row.latest_month),
    },
  ];

  const creditColumns: readonly Column<ApiLedgerCredit>[] = [
    {
      key: 'resource',
      header: 'Resource',
      render: (row) => row.resource_id ?? 'not visible to you',
    },
    { key: 'owner', header: 'Owner', render: (row) => row.owner },
    { key: 'closed', header: 'Closed by', render: (row) => row.closed_by },
    {
      key: 'verified',
      header: 'Verified a month',
      numeric: true,
      render: (row) => (
        <Figure
          value={{ kind: 'measured', amount: Number(row.verified_monthly_saving) }}
          freshness={freshness}
        />
      ),
    },
    {
      key: 'held',
      header: 'Held so far',
      numeric: true,
      render: (row) => (
        <Figure
          value={{ kind: 'measured', amount: Number(row.saving_held) }}
          freshness={freshness}
        />
      ),
    },
    {
      key: 'months',
      header: 'Months',
      prose: true,
      render: (row) => (
        <span data-testid={`months-${row.credit_id}`}>
          {monthsInWords(row.months)}
          {row.regressed ? '. Stopped: a month cost as much as before' : ''}
        </span>
      ),
    },
  ];

  return (
    <section aria-label="Savings ledger">
      <p>
        Each saving verified against the bill is credited to the team named for its resource,
        and every closed month since adds what the bill showed it still saving. A month that
        cost as much as before stops the credit there. Choose a team to see its credits
      </p>
      <StateBoundary state={state}>
        <DataTable
          rows={teams}
          columns={teamColumns}
          rowKey={(row) => row.team ?? NO_TEAM}
          caption={`${String(teams.length)} ${
            teams.length === 1 ? 'team' : 'teams'
          } by the saving their verified changes held, measured`}
        />
      </StateBoundary>
      {chosen === undefined ? null : (
        <section aria-label={`${teamName(chosen)} credits`} data-testid="ledger-credits">
          <h2>{teamName(chosen)}</h2>
          <DataTable
            rows={shown}
            columns={creditColumns}
            rowKey={(row) => row.credit_id}
            caption={`${String(shown.length)} verified ${
              shown.length === 1 ? 'saving' : 'savings'
            } credited to ${teamName(chosen)}, the most held first`}
          />
        </section>
      )}
    </section>
  );
}
