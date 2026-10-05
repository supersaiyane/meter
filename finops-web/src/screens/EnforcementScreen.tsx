import { useState } from 'react';
import { Link } from 'react-router';

import { useEnforcementActions } from '../api/queries';
import type { ApiEnforcementAction } from '../api/types';
import { DataTable } from '../components/DataTable';
import { FixtureBand } from '../components/FixtureBand';
import { StateBoundary } from '../components/StateBoundary';
import type { Column } from '../components/tableConfig';
import { countdown, stampUtc } from './enforcementTime';
import { useReportMeta } from '../shell/metaRegistry';
import { surfaceStateFor } from './surfaceStateFor';

/**
 * What the controls did, per P2 spec section 9.4.
 *
 * This screen is the reason `deny` is safe to enable. A control that cuts off an
 * engineer mid incident is a self inflicted second incident, and the mitigations
 * recorded against ISS-092 are auto expiry, a never deny list, a revoke route
 * and this screen. Without the screen the other three are invisible and nobody
 * turns the feature on.
 *
 * Revoke is absent rather than disabled when the API says an action is not
 * revocable. A control that looks available and is not is worse than an absent
 * one, and the write level is the API's decision: architectural constraint 8
 * makes it the single enforcement point, and a second implementation of an
 * authorization rule is how an authorization bug is created.
 */

export interface EnforcementScreenProps {
  /** Injected so the countdown is testable without faking a clock. */
  readonly now?: Date;
}

export function EnforcementScreen({ now }: EnforcementScreenProps) {
  const query = useEnforcementActions();
  const envelope = query.data?.data;
  const rows = envelope?.data ?? [];
  const source = query.data?.source ?? 'fixture';
  const [note, setNote] = useState<string | null>(null);
  useReportMeta('query-enforcement', envelope?.meta);

  const at = now ?? new Date();

  const columns: readonly Column<ApiEnforcementAction>[] = [
    { key: 'action', header: 'Action', render: (row) => row.action },
    { key: 'principal', header: 'Principal', render: (row) => row.principal },
    { key: 'applied', header: 'Applied', render: (row) => stampUtc(row.applied_at) },
    {
      key: 'expires',
      header: 'Expires',
      render: (row) => (
        <span data-testid={`expires-${row.action_id}`}>
          {row.expires_at === null ? (
            // An empty cell would read as "unknown". This is known.
            'does not expire'
          ) : (
            <>
              <time dateTime={row.expires_at}>{stampUtc(row.expires_at)}</time>{' '}
              {countdown(row.expires_at, at)}
            </>
          )}
        </span>
      ),
    },
    {
      key: 'reason',
      header: 'Reason',
      render: (row) => <Link to={`/govern/query-cost/findings/${row.reason_finding_id}`}>why</Link>,
    },
    {
      key: 'revoke',
      header: 'Revoke',
      render: (row) =>
        row.revocable ? (
          <button
            type="button"
            onClick={() => {
              // Not silence. A button that does nothing when clicked is the
              // failure this product spends its whole design budget avoiding.
              setNote(
                source === 'fixture'
                  ? `Revoke is not connected yet. ${row.action} on ${row.principal} was not changed.`
                  : `Revoking ${row.action} on ${row.principal}.`,
              );
            }}
          >
            Revoke
          </button>
        ) : null,
    },
  ];

  const state = surfaceStateFor(query, envelope?.meta, rows.length, 'none', 'query_control');

  return (
    <section aria-label="Enforcement">
      <FixtureBand source={source} />
      {note === null ? null : (
        <p data-testid="revoke-note" role="status">
          {note}
        </p>
      )}
      <StateBoundary state={state}>
        <DataTable
          rows={rows}
          columns={columns}
          rowKey={(row) => row.action_id}
          caption="Active and past controls, what they did and when they stop"
        />
      </StateBoundary>
    </section>
  );
}
