import { useId, useMemo, useState } from 'react';

import { useChosenAccount } from '../api/account';
import { useEstimates, useMe } from '../api/queries';
import type { ApiPlanEstimate } from '../api/types';
import { DataTable } from '../components/DataTable';
import { Figure } from '../components/Figure';
import { FreshnessIndicator } from '../components/FreshnessIndicator';
import { StateBoundary } from '../components/StateBoundary';
import type { Column } from '../components/tableConfig';
import { useReportMeta } from '../shell/metaRegistry';
import { dayName, freshnessOf } from './commitmentFormat';
import { EstimateAccuracyPanel } from './EstimateAccuracyPanel';
import { EstimateLinesPanel } from './EstimateLinesPanel';
import { commentState, planState, pullRequestName, unpricedSentence } from './estimatesModel';
import { surfaceStateFor } from './surfaceStateFor';

/**
 * Estimates, under Plan. FEAT-095 to 097, TASK-P16-008.
 *
 * Each plan a pull request's pipeline sent, priced from list prices before it is applied, the
 * changes Meter could not price counted first, then how close the estimates came once the bill
 * covered thirty days of what a merged plan created. A plan names no account until it is applied,
 * so all of it is the organization's, ADR-0025, and anyone else is told why rather than shown an
 * error. Every estimate is modelled; the bill it is set against is measured.
 */
export function EstimatesScreen() {
  const me = useMe();
  const chosen = useChosenAccount();
  const organization = me.data?.data.is_global === true && chosen === null;
  const [planId, setPlanId] = useState<string | null>(null);
  return (
    <section aria-label="Estimates">
      <p data-testid="estimates-note">
        Each plan is priced from AWS's on demand list prices before it is applied, and its
        estimate is written on its pull request. Once a merged plan's resources have run thirty
        billed days, the bill says how close the estimate came
      </p>
      {me.isPending ? null : organization ? (
        <>
          <PlansPanel chosen={planId} choose={setPlanId} />
          {planId === null ? null : <EstimateLinesPanel planId={planId} />}
          <EstimateAccuracyPanel />
        </>
      ) : (
        <p data-testid="estimates-organization-only">
          A plan names no account until it is applied, so its estimate belongs to the
          organization and shows to a reader whose scope is the whole organization, with no
          account chosen
        </p>
      )}
    </section>
  );
}

function money(value: string | null, freshness: ReturnType<typeof freshnessOf>) {
  return value === null ? (
    'Not priced'
  ) : (
    <Figure value={{ kind: 'modelled', amount: Number(value) }} freshness={freshness} />
  );
}

function planColumns(
  freshness: ReturnType<typeof freshnessOf>,
  chosen: string | null,
  choose: (planId: string) => void,
): readonly Column<ApiPlanEstimate>[] {
  return [
    {
      key: 'pull-request',
      header: 'Pull request',
      rowHeader: true,
      render: pullRequestName,
      sortValue: pullRequestName,
    },
    {
      key: 'unpriced',
      header: 'Not priced',
      prose: true,
      cellTestId: 'plan-unpriced',
      render: (row) =>
        row.unpriced_lines === null || row.priced_lines === null
          ? planState(row)
          : unpricedSentence(row.unpriced_lines, row.unpriced_lines + row.priced_lines),
    },
    {
      key: 'change',
      header: 'Monthly change',
      numeric: true,
      render: (row) => money(row.monthly_change, freshness),
      sortValue: (row) => (row.monthly_change === null ? null : Number(row.monthly_change)),
    },
    {
      key: 'after',
      header: 'Monthly after',
      numeric: true,
      render: (row) => money(row.monthly_after, freshness),
    },
    {
      key: 'commit',
      header: 'Commit',
      render: (row) => <code>{row.head_sha.slice(0, 12)}</code>,
    },
    {
      key: 'received',
      header: 'Received',
      render: (row) => dayName(row.received_at),
      sortValue: (row) => row.received_at,
    },
    {
      key: 'comment',
      header: 'Comment',
      prose: true,
      render: (row) =>
        row.comment_url === null ? (
          commentState(row)
        ) : (
          <a href={row.comment_url}>{commentState(row)}</a>
        ),
    },
    {
      key: 'state',
      header: 'Pull request state',
      render: (row) => row.pull_request_state ?? 'Not yet read',
    },
    {
      key: 'open',
      header: 'Lines',
      render: (row) =>
        row.status === 'PRICED' ? (
          <button
            type="button"
            aria-pressed={chosen === row.plan_id}
            data-testid={`open-plan-${row.plan_id}`}
            onClick={() => {
              choose(row.plan_id);
            }}
          >
            Show its lines
          </button>
        ) : null,
    },
  ];
}

function PlansPanel({
  chosen,
  choose,
}: {
  readonly chosen: string | null;
  readonly choose: (planId: string) => void;
}) {
  const heading = useId();
  const query = useEstimates(true);
  const envelope = query.data;
  const plans = useMemo(() => envelope?.data.plans ?? [], [envelope]);
  useReportMeta('estimates', envelope?.meta);
  const state = surfaceStateFor(query, envelope?.meta, plans.length, 'none', 'plan_estimates');
  const freshness = freshnessOf(envelope?.meta);
  return (
    <section className="meter-panel" aria-labelledby={heading} data-testid="estimate-plans">
      <h2 id={heading}>Plans</h2>
      <p>
        Every plan received, the newest first, with its estimate a month, modelled
        {envelope?.meta.as_of ? <FreshnessIndicator freshness={freshness} /> : null}
      </p>
      {envelope?.data.more === true ? (
        <p data-testid="estimate-plans-more">
          Only the newest {String(plans.length)} plans are listed. Older ones are kept for 400
          days and are not shown here
        </p>
      ) : null}
      <StateBoundary state={state}>
        <DataTable
          rows={plans}
          columns={planColumns(freshness, chosen, choose)}
          rowKey={(row) => row.plan_id}
          caption={`${String(plans.length)} plans, the newest first`}
        />
      </StateBoundary>
    </section>
  );
}
