import { useMemo } from 'react';

import { useCostCommitments } from '../api/queries';
import { DataTable } from '../components/DataTable';
import { Figure } from '../components/Figure';
import { StateBoundary } from '../components/StateBoundary';
import type { Column } from '../components/tableConfig';
import { useReportMeta } from '../shell/metaRegistry';
import { surfaceStateFor } from './surfaceStateFor';
import { riskLabel, type RiskVerdict } from '../components/actionRisk';
import { SeverityBadge } from '../components/SeverityBadge';
import { severityLevel } from './querySeverity';
import type {
  ApiCommitmentAction,
  ApiCommitmentCoverage,
  ApiCommitmentUse,
} from '../api/types';

/**
 * What was committed, what it consumed, and what it covered. FEAT-024.
 *
 * The whole design problem on this screen is that two percentages sit near each
 * other and mean opposite things, and a reader who conflates them draws the
 * wrong conclusion with confidence.
 *
 * Utilization asks how much of what we already paid for was consumed. Coverage
 * asks how much of the estate that could have been on a commitment actually was.
 * A plan at full utilization covering a tenth of the estate says buy more. A plan
 * at half utilization covering everything says the last purchase was too large.
 * So they are two tables under two headings, each saying in words what its
 * percentage is a percentage of, and they are never placed in adjacent columns of
 * one table where the eye would compare them.
 *
 * A missing percentage is a sentence, never a zero. A commitment that has not
 * started has consumed nothing of nothing, and rendering that as zero percent
 * would say the money was wasted.
 */

function money(amount: string): number {
  return Number(amount);
}

/** A fraction as a percentage, or the sentence that belongs where there is none. */
function share(value: string | null, absent: string): string {
  if (value === null) {
    return absent;
  }
  return `${(Number(value) * 100).toFixed(1)}%`;
}

/** Every commitment. Nothing stops to buy one, which is exactly why it reads as safe, and
 *  it cannot be handed back. The least reversible finding in the product. */
const COMMITMENT_RISK: RiskVerdict = {
  reversible: false,
  disturbs_running_work: false,
  is_no_regret: false,
};

export function CostCommitmentsScreen() {
  const query = useCostCommitments();
  const envelope = query.data?.data;
  const found = envelope?.data;
  const commitments = useMemo(() => found?.commitments ?? [], [found]);
  const coverage = useMemo(() => found?.coverage ?? [], [found]);
  const actions = useMemo(() => found?.actions ?? [], [found]);

  useReportMeta('cost-commitments', envelope?.meta);
  const state = surfaceStateFor(
    query,
    envelope?.meta,
    commitments.length,
    'none',
    'commitment_use',
  );

  const freshness = {
    asOf: new Date(envelope?.meta.as_of ?? 0),
    collectedAt: new Date(envelope?.meta.collected_at ?? 0),
  };

  const used: readonly Column<ApiCommitmentUse>[] = [
    { key: 'commitment', header: 'Commitment', render: (row) => row.commitment_id },
    { key: 'type', header: 'Kind', render: (row) => row.commitment_type },
    {
      key: 'status',
      header: 'State',
      // Expired is shown, not filtered. The money was spent, and the coverage gap
      // the expiry leaves is the finding.
      render: (row) => row.status,
    },
    {
      key: 'utilization',
      header: 'Of what we paid for, used',
      numeric: true,
      render: (row) => (
        <span data-testid={`utilization-${row.commitment_id}`}>
          {share(row.utilization, 'not started')}
        </span>
      ),
    },
    {
      key: 'committed',
      header: 'Committed',
      numeric: true,
      render: (row) => (
        <Figure
          value={{ kind: 'measured', amount: money(row.committed) }}
          freshness={freshness}
        />
      ),
    },
    {
      key: 'wasted',
      header: 'Paid for and unused',
      numeric: true,
      // In money, because that is the number somebody can act on. A percentage
      // alone does not say whether it is worth a morning.
      render: (row) => (
        <Figure value={{ kind: 'measured', amount: money(row.wasted) }} freshness={freshness} />
      ),
    },
  ];

  const covered: readonly Column<ApiCommitmentCoverage>[] = [
    { key: 'service', header: 'Service', render: (row) => row.dimension_value },
    { key: 'type', header: 'Kind of commitment', render: (row) => row.commitment_type },
    {
      key: 'coverage',
      header: 'Of what could be committed, is',
      numeric: true,
      render: (row) => (
        <span data-testid={`coverage-${row.dimension_value}`}>
          {share(row.coverage, 'nothing eligible')}
        </span>
      ),
    },
    {
      key: 'eligible',
      header: 'Could be committed',
      numeric: true,
      render: (row) => (
        <Figure
          value={{ kind: 'measured', amount: money(row.eligible_spend) }}
          freshness={freshness}
        />
      ),
    },
    {
      key: 'uncovered',
      header: 'On demand instead',
      numeric: true,
      // The gap, in money. A reader buying against this row needs the amount, not
      // the percentage it works out to.
      render: (row) => (
        <Figure
          value={{
            kind: 'measured',
            amount: money(row.eligible_spend) - money(row.covered_spend),
          }}
          freshness={freshness}
        />
      ),
    },
  ];

  return (
    <section aria-label="Commitments">
      {/*
        Outside the boundary, like the anomalies screen and for the same reason:
        this sentence is about what the screen can answer at all, and the boundary
        takes over the moment there are no rows.
      */}
      <p data-testid="commitment-scope-note">
        A commitment is bought by the payer and consumed by whichever accounts ran the usage,
        and no provider reports which. These figures are for the whole payer and cannot be
        narrowed to a subset of accounts
      </p>

      {found ? (
        <p data-testid="commitment-waste">
          Paid for and unused in this window:{' '}
          <Figure
            value={{ kind: 'measured', amount: money(found.wasted_total) }}
            freshness={freshness}
          />
        </p>
      ) : null}

      <StateBoundary state={state}>
        <>
          <h2 data-testid="utilization-heading">How much of what we paid for was used</h2>
          <p data-testid="utilization-explains">
            Per commitment. A commitment at a hundred percent was correctly sized. It says
            nothing about how much of the estate is on a commitment
          </p>
          <DataTable
            rows={commitments}
            columns={used}
            rowKey={(row) => row.commitment_id}
            caption={`${String(commitments.length)} commitments, most unused money first`}
          />

          <h2 data-testid="coverage-heading">How much of the estate is on a commitment</h2>
          <p data-testid="coverage-explains">
            Per service, never per commitment, because a covered dollar cannot be attributed to
            one of several overlapping plans. A low figure here says buy, whatever the
            utilization above says
          </p>
          <DataTable
            rows={coverage}
            columns={covered}
            rowKey={(row) => `${row.commitment_type}:${row.dimension_value}`}
            caption={`${String(coverage.length)} services, most on demand spend first`}
          />

          {/* FEAT-055. The gap above, as something somebody owns. The coverage table answers
              how much is uncovered and this answers what to do about it, which is the
              difference between a fact and a decision. */}
          <h2 data-testid="actions-heading">What to do about the gap</h2>
          {actions.length === 0 ? (
            // Said, not blank, and carefully not called full coverage. Every gap being below
            // the configured minimum saving is a different claim from there being no gap, and
            // the coverage table above is where a reader checks which.
            <p data-testid="actions-empty">
              No coverage gap is large enough to be worth a commitment at the configured
              minimum. That is not the same as full coverage: the table above says how much is
              uncovered.
            </p>
          ) : (
            <table data-testid="actions">
              <caption>
                {actions.length === 1
                  ? 'One gap worth committing to, with what being wrong would cost.'
                  : `${String(actions.length)} gaps worth committing to, worst money first, ` +
                    'with what being wrong would cost.'}
              </caption>
              <thead>
                <tr>
                  <th scope="col">Gap</th>
                  <th scope="col">Saving a month</th>
                  <th scope="col">Severity</th>
                  <th scope="col">If it is wrong</th>
                </tr>
              </thead>
              <tbody>
                {actions.map((row: ApiCommitmentAction) => (
                  <tr key={`${row.commitment_type}:${row.dimension}:${row.dimension_value}`}>
                    <th scope="row">
                      {row.dimension_value}
                      <span> {row.commitment_type}</span>
                    </th>
                    <td>
                      {/* Modelled, never measured, and the rationale says the discount came
                          from configuration rather than from a quote. */}
                      <Figure
                        value={{
                          kind: 'modelled',
                          amount: Number(row.estimated_monthly_saving),
                        }}
                        freshness={freshness}
                        unit="usd"
                      />
                    </td>
                    <td>
                      <SeverityBadge level={severityLevel(row.severity)} />
                    </td>
                    <td>
                      {/* The same two words the waste screen and the home panel use, from the
                          same module, so a reader is not told a change is permanent in one
                          place and reversible in another. A commitment is the least
                          reversible thing in the product. */}
                      {/* Constant, and correct by construction rather than by a flag on the
                          row: every commitment is permanent and none of them stops anything.
                          Through the shared module so the wording matches the waste screen. */}
                      <strong>{riskLabel(COMMITMENT_RISK)}</strong>
                      {/* The floor is the decision. A commitment obligates its whole term
                          whether or not the usage continues. */}
                      <span>
                        {' '}
                        Worth it while usage stays above {row.usage_floor_percent} percent of
                        today's for {row.term_months} months.
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      </StateBoundary>
    </section>
  );
}
