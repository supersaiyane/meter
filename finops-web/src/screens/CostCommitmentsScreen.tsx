import { useMemo } from 'react';
import { commitmentTypeName } from '../components/displayNames';

import { useChosenAccount } from '../api/account';
import { useCommitmentDays, useCostCommitments, useMe } from '../api/queries';
import { ChartPanel } from '../components/ChartPanel';
import { Heatmap, StackedArea } from '../components/charts';
import { DataTable } from '../components/DataTable';
import { PercentCell } from '../components/PercentCell';
import { Figure } from '../components/Figure';
import { StateBoundary } from '../components/StateBoundary';
import type { Column } from '../components/tableConfig';
import { useReportMeta } from '../shell/metaRegistry';
import { committedEachDay, coverageEachDay, dayByDay } from './commitmentDays';
import { surfaceStateFor } from './surfaceStateFor';
import { CalendarPanel, InventoryPanel } from './CommitmentHoldingsPanels';
import { PurchasePlanPanel } from './PurchasePlanPanel';
import { SavingsRatePanel } from './SavingsRatePanel';
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
 *
 * P14, TASK-P14-009. The screen opens on the effective savings rate, measured from
 * the bill, and closes on what the payer holds, when it ends, and what to buy:
 * Meter's plan beside AWS's. Those three are the payer's alone, ADR-0025, so they
 * are read only for a reader whose scope is the whole organization with no account
 * chosen, and anyone else is told why rather than shown an error.
 */

function money(amount: string): number {
  return Number(amount);
}

/**
 * A fraction, or null where the row has none.
 *
 * It used to format the percentage itself and return the absent sentence as a string, which made
 * the two indistinguishable to everything downstream: a caller could not draw a bar without
 * parsing its own output back, and a sentence and a measurement rendered identically. The null
 * now travels, and `PercentCell` decides what an absence looks like.
 */
function share(value: string | null): number | null {
  return value === null ? null : Number(value);
}

/** Every commitment. Nothing stops to buy one, which is exactly why it reads as safe, and
 *  it cannot be handed back. The least reversible finding in the product. */
const COMMITMENT_RISK: RiskVerdict = {
  reversible: false,
  disturbs_running_work: false,
  is_no_regret: false,
};

/** FEAT-055's gaps as somebody's to act on, TASK-P8-013 on `DataTable`. */
function actionColumns(freshness: {
  readonly asOf: Date;
  readonly collectedAt: Date;
}): readonly Column<ApiCommitmentAction>[] {
  return [
    {
      key: 'gap',
      header: 'Gap',
      rowHeader: true,
      render: (row) => (
        <>
          {row.dimension_value}
          <span> {commitmentTypeName(row.commitment_type)}</span>
        </>
      ),
      sortValue: (row) => row.dimension_value,
    },
    {
      key: 'saving',
      header: 'Estimated monthly savings',
      numeric: true,
      // Modelled, never measured, and the rationale says the discount came from configuration
      // rather than from a quote. So is the total, hatched like every figure it adds up.
      render: (row) => (
        <Figure
          value={{ kind: 'modelled', amount: Number(row.estimated_monthly_saving) }}
          freshness={freshness}
          unit="usd"
        />
      ),
      sortValue: (row) => Number(row.estimated_monthly_saving),
      total: {
        value: (row) => Number(row.estimated_monthly_saving),
        unit: () => 'USD',
        provenance: () => 'modelled',
        render: (sum) => (
          <Figure value={{ kind: 'modelled', amount: sum }} freshness={freshness} unit="usd" />
        ),
      },
    },
    {
      key: 'severity',
      header: 'Severity',
      render: (row) => <SeverityBadge level={severityLevel(row.severity)} />,
      sortValue: (row) => severityLevel(row.severity),
    },
    {
      key: 'risk',
      header: 'If it is wrong',
      prose: true,
      // Constant, and correct by construction rather than by a flag on the row: every
      // commitment is permanent and none of them stops anything. Through the shared module so
      // the wording matches the waste screen. The floor is the decision: a commitment
      // obligates its whole term whether or not the usage continues.
      render: (row) => (
        <>
          <strong>{riskLabel(COMMITMENT_RISK)}</strong>
          <span>
            {' '}
            Worth it while usage stays above {row.usage_floor_percent} percent of today's for{' '}
            {row.term_months} months.
          </span>
        </>
      ),
    },
  ];
}

/** Whole dollars, what a chart of a month's commitments can show. */
function dollars(value: number): string {
  return `$${value.toLocaleString('en-GB', { maximumFractionDigits: 0 })}`;
}

export function CostCommitmentsScreen() {
  const me = useMe();
  const chosen = useChosenAccount();
  const payer = me.data?.data.is_global === true && chosen === null;
  const query = useCostCommitments();
  const envelope = query.data?.data;
  const found = envelope?.data;
  const commitments = useMemo(() => found?.commitments ?? [], [found]);
  const coverage = useMemo(() => found?.coverage ?? [], [found]);
  const actions = useMemo(() => found?.actions ?? [], [found]);

  useReportMeta('cost-commitments', envelope?.meta);

  // TASK-P8-013. The same commitments a day at a time, read for the three charts.
  const daily = useCommitmentDays();
  useReportMeta('cost-commitment-days', daily.data?.meta);
  const days = useMemo(() => daily.data?.data ?? [], [daily.data]);
  const daysState = surfaceStateFor(daily, daily.data?.meta, days.length, 'none', 'commitment');
  const usedByDay = useMemo(() => committedEachDay(days), [days]);
  const coveredByDay = useMemo(() => coverageEachDay(days), [days]);
  const grid = useMemo(() => dayByDay(days), [days]);

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
      header: 'Commitment utilization',
      numeric: true,
      render: (row) => (
        <span data-testid={`utilization-${row.commitment_id}`}>
          {/* Measured off the bill, not modelled. A commitment that has not started reads
              as those words and never as nought percent, which would say the money was
              wasted rather than that nothing has happened yet. */}
          <PercentCell
            fraction={share(row.utilization)}
            absent="not started"
            provenance="measured"
          />
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
      header: 'Unused commitment',
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
    {
      key: 'type',
      header: 'Commitment discount type',
      render: (row) => commitmentTypeName(row.commitment_type),
    },
    {
      key: 'coverage',
      header: 'Commitment coverage',
      numeric: true,
      render: (row) => (
        <span data-testid={`coverage-${row.dimension_value}`}>
          {/* A fraction of what could be committed, so it is a bar against a hundred and
              never a share of a total. Two services at eighty percent are both at eighty
              percent and neither is half of anything. */}
          <PercentCell
            fraction={share(row.coverage)}
            absent="nothing eligible"
            provenance="measured"
          />
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
      header: 'On-Demand cost',
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
      <SavingsRatePanel />
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

      {/* Over time before the window's detail. Money is stacked where its total means
          something, what was committed and what could have been covered, and the two
          percentages go to the heatmap, because two utilizations added together measure
          nothing. */}
      <StateBoundary state={daysState} coverageShownElsewhere>
        <div data-testid="chart-row">
          <ChartPanel
            id="commitments-use"
            title="Use, each day"
            caption="What every commitment obliged each day, as used and as paid for and unused. The last thirty days"
          >
            <StackedArea
              periods={usedByDay.periods}
              series={usedByDay.series.map((one) => ({
                ...one,
                provenance: 'measured' as const,
              }))}
              label="Commitment money each day, used and unused"
              format={dollars}
            />
          </ChartPanel>
          <ChartPanel
            id="commitments-coverage"
            title="Coverage, each day"
            caption="Spend a commitment could have covered each day, as covered and as left on demand"
          >
            <StackedArea
              periods={coveredByDay.periods}
              series={coveredByDay.series.map((one) => ({
                ...one,
                provenance: 'measured' as const,
              }))}
              label="Eligible spend each day, covered and on demand"
              format={dollars}
            />
          </ChartPanel>
        </div>
        <ChartPanel
          id="commitments-day-by-day"
          title="Day by day"
          caption="Each kind's utilization and coverage per day, in percent, darker for higher. An outline is a day with nothing to divide by"
        >
          <Heatmap
            rows={grid.rows}
            columns={grid.columns}
            values={grid.values}
            provenance="measured"
            label="Utilization and coverage by kind and day, percent"
            format={(value) => `${value.toFixed(0)} percent`}
            missing="nothing to divide by"
          />
        </ChartPanel>
      </StateBoundary>

      <StateBoundary state={state}>
        <>
          <h2 data-testid="utilization-heading">Commitment utilization</h2>
          <p data-testid="utilization-means">How much of what we paid for was used</p>
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

          <h2 data-testid="coverage-heading">Commitment coverage</h2>
          <p data-testid="coverage-means">How much of the estate is on a commitment</p>
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
            <div data-testid="actions">
              <DataTable
                rows={actions}
                columns={actionColumns(freshness)}
                rowKey={(row) =>
                  `${row.commitment_type}:${row.dimension}:${row.dimension_value}`
                }
                caption={
                  actions.length === 1
                    ? 'One gap worth committing to, with what being wrong would cost.'
                    : `${String(actions.length)} gaps worth committing to, worst money first, ` +
                      'with what being wrong would cost.'
                }
                initialSort={{ key: 'saving', direction: 'descending' }}
              />
            </div>
          )}
        </>
      </StateBoundary>

      {me.isPending ? null : payer ? (
        <>
          <InventoryPanel />
          <CalendarPanel />
          <PurchasePlanPanel mayAct={payer} />
        </>
      ) : (
        <p data-testid="commitment-payer-only">
          What the payer holds, when it ends and what to buy belong to the payer alone, so they
          show to a reader whose scope is the whole organization, with no account chosen
        </p>
      )}
    </section>
  );
}
