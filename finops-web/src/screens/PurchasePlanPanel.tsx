import { useId, useMemo } from 'react';

import { useCommitmentPlans } from '../api/queries';
import type { ApiPlanLine, ApiProviderRecommendation, ApiPurchasePlan } from '../api/types';
import { DataTable } from '../components/DataTable';
import { Figure } from '../components/Figure';
import { FreshnessIndicator } from '../components/FreshnessIndicator';
import { StateBoundary } from '../components/StateBoundary';
import type { Column } from '../components/tableConfig';
import { useReportMeta } from '../shell/metaRegistry';
import { dayName, freshnessOf, monthName } from './commitmentFormat';
import { PlanActions } from './PlanActions';
import { surfaceStateFor } from './surfaceStateFor';

/**
 * Meter's purchase plan beside AWS's recommendations, and why they differ. FEAT-089 and FEAT-090,
 * OPEN-35 and OPEN-40, TASK-P14-009.
 *
 * The screen does not choose between them. Every figure in Meter's plan is modelled, from the bill
 * and P9's rates, and AWS's saving is AWS's own estimate, so each says so. What approving buys is
 * this month's tranche; the later tranches are named so the ladder can be seen.
 */

type Freshness = ReturnType<typeof freshnessOf>;

const PROGRAMS: Readonly<Record<string, string>> = {
  EC2Instance: 'EC2 Instance Savings Plan',
  Compute: 'Compute Savings Plan',
};

const STATUS: Readonly<Record<string, string>> = {
  DRAFT: 'Draft',
  APPROVED: 'Approved',
  BOUGHT: 'Bought, not yet seen in full',
  VERIFIED: 'Verified',
  WITHDRAWN: 'Withdrawn',
  LAPSED: 'Lapsed',
};

function modelled(amount: string, freshness: Freshness, unit: 'usd' | 'usd-unit' = 'usd') {
  return (
    <Figure
      value={{ kind: 'modelled', amount: Number(amount) }}
      freshness={freshness}
      unit={unit}
    />
  );
}

function lineColumns(
  plan: ApiPurchasePlan,
  freshness: Freshness,
): readonly Column<ApiPlanLine>[] {
  const bought = plan.status === 'BOUGHT' || plan.status === 'VERIFIED';
  return [
    {
      key: 'tranche',
      header: 'Tranche',
      rowHeader: true,
      render: (row) =>
        row.tranche_month === plan.plan_month
          ? `${monthName(row.tranche_month)}, to buy now`
          : monthName(row.tranche_month),
      sortValue: (row) => row.tranche_month,
    },
    {
      key: 'program',
      header: 'Buys',
      render: (row) =>
        row.instance_family === null
          ? (PROGRAMS[row.program] ?? row.program)
          : `${PROGRAMS[row.program] ?? row.program}, ${row.instance_family} in ${row.region_id ?? ''}`,
    },
    {
      key: 'hourly',
      header: 'Commitment an hour',
      numeric: true,
      render: (row) => modelled(row.hourly_commitment, freshness, 'usd-unit'),
      sortValue: (row) => Number(row.hourly_commitment),
      total: {
        value: (row) => Number(row.hourly_commitment),
        unit: () => 'USD an hour',
        provenance: () => 'modelled',
        render: (sum) => modelled(String(sum), freshness, 'usd-unit'),
      },
    },
    {
      key: 'discount',
      header: 'Discount',
      numeric: true,
      render: (row) => `${Number(row.discount_percent).toFixed(1)} percent`,
    },
    {
      key: 'saving',
      header: 'Saving a month',
      numeric: true,
      render: (row) => modelled(row.monthly_saving, freshness),
    },
    {
      key: 'floor',
      header: 'If usage falls',
      prose: true,
      // FEAT-055's honest figure: below this the commitment costs more than it saves.
      render: (row) => `Worth it while usage stays above ${row.usage_floor_percent} percent`,
    },
    {
      key: 'upfront',
      header: 'Paid up front',
      numeric: true,
      render: (row) => modelled(row.upfront_cost, freshness),
    },
    ...(bought
      ? [
          {
            key: 'seen',
            header: 'Seen in the inventory',
            render: (row: ApiPlanLine) =>
              row.tranche_month !== plan.plan_month
                ? 'Not bought in this plan'
                : (row.matched_commitment_id ?? 'Not yet seen'),
          },
        ]
      : []),
  ];
}

function providerColumns(freshness: Freshness): readonly Column<ApiProviderRecommendation>[] {
  return [
    {
      key: 'program',
      header: 'For',
      rowHeader: true,
      render: (row) =>
        row.kind === 'savings_plan' ? (PROGRAMS[row.program] ?? row.program) : row.program,
    },
    {
      key: 'advice',
      header: 'AWS recommends',
      prose: true,
      // A failure is its cause, never advice to buy nothing; advice to buy nothing is an answer.
      render: (row) => {
        if (row.failure_cause !== null) {
          return `Could not be read: ${row.failure_cause}`;
        }
        if (row.recommended !== true) {
          return 'Buying nothing';
        }
        return row.hourly_commitment !== null ? (
          <>{modelled(row.hourly_commitment, freshness, 'usd-unit')} an hour</>
        ) : (
          `${row.units ?? '0'} instances or nodes`
        );
      },
    },
    {
      key: 'saving',
      header: "Saving a month, AWS's estimate",
      numeric: true,
      render: (row) =>
        row.estimated_monthly_savings === null
          ? ''
          : modelled(row.estimated_monthly_savings, freshness),
    },
    {
      key: 'lookback',
      header: 'Looked back',
      render: (row) => (row.failure_cause === null ? `${String(row.lookback_days)} days` : ''),
    },
  ];
}

export function PurchasePlanPanel({ mayAct }: { readonly mayAct: boolean }) {
  const heading = useId();
  const query = useCommitmentPlans(true);
  const envelope = query.data;
  const found = envelope?.data;
  useReportMeta('commitment-plans', envelope?.meta);
  const plan = found?.plan ?? null;
  const lines = useMemo(() => found?.lines ?? [], [found]);
  const provider = useMemo(() => found?.provider ?? [], [found]);
  const rows = plan === null ? provider.length : 1;
  const state = surfaceStateFor(query, envelope?.meta, rows, 'none', 'purchase_plan');
  const freshness = freshnessOf(envelope?.meta);
  const buysThisMonth =
    plan !== null && lines.some((line) => line.tranche_month === plan.plan_month);

  return (
    <section className="meter-panel" aria-labelledby={heading} data-testid="purchase-plans">
      <h2 id={heading}>What to buy</h2>
      <p>
        Meter&apos;s plan beside AWS&apos;s recommendation. Every figure in both is modelled,
        and AWS&apos;s saving is its own estimate
        {envelope?.meta.as_of ? <FreshnessIndicator freshness={freshness} /> : null}
      </p>
      {found?.no_plan_reason ? <p data-testid="no-plan">{found.no_plan_reason}</p> : null}
      <StateBoundary state={state}>
        {plan !== null ? (
          <>
            <h3 data-testid="plan-heading">
              Meter&apos;s plan for {monthName(plan.plan_month)}:{' '}
              {STATUS[plan.status] ?? plan.status}
            </h3>
            <p data-testid="plan-basis">
              Drawn from {String(plan.days_held)} days of the bill, {dayName(plan.window_start)}{' '}
              to {dayName(plan.window_end)}, under the policy:{' '}
              {Number(plan.target_coverage) * 100} percent of the steady baseline,{' '}
              {String(plan.term_years)} year, {plan.payment_option.toLowerCase()}.
            </p>
            {plan.no_purchase_reason !== null ? (
              <p data-testid="plan-nothing">{plan.no_purchase_reason}</p>
            ) : null}
            {found && found.difference.length > 0 ? (
              <>
                <h3>Why the two differ</h3>
                <ul data-testid="plan-difference">
                  {found.difference.map((sentence) => (
                    <li key={sentence}>{sentence}</li>
                  ))}
                </ul>
              </>
            ) : null}
            {lines.length > 0 ? (
              <DataTable
                rows={lines}
                columns={lineColumns(plan, freshness)}
                rowKey={(row) => String(row.line_no)}
                caption="Meter's plan, by tranche. Approving buys this month's; the later tranches keep the ladder"
              />
            ) : null}
            {plan.unpriced.length > 0 ? (
              <>
                <h3>Not priced</h3>
                <ul data-testid="plan-unpriced">
                  {plan.unpriced.map((one) => (
                    <li key={`${one.instance_family ?? 'moving'}:${one.region_id ?? ''}`}>
                      {one.instance_family === null
                        ? 'Usage that moves between families'
                        : `${one.instance_family} in ${one.region_id ?? ''}`}
                      , {one.steady_hourly} USD an hour of steady usage: {one.reason}. Not
                      priced, and not counted as nothing.
                    </li>
                  ))}
                </ul>
              </>
            ) : null}
            <PlanActions plan={plan} mayAct={mayAct} buysThisMonth={buysThisMonth} />
            {found && found.events.length > 0 ? (
              <>
                <h3>Steps taken</h3>
                <ol data-testid="plan-steps">
                  {found.events.map((one) => (
                    <li key={`${one.at}:${one.to_status}`}>
                      {STATUS[one.to_status] ?? one.to_status} by {one.principal},{' '}
                      {dayName(one.at)}
                      {one.note ? `: ${one.note}` : ''}
                    </li>
                  ))}
                </ol>
              </>
            ) : null}
          </>
        ) : null}
        {provider.length > 0 ? (
          <DataTable
            rows={provider}
            columns={providerColumns(freshness)}
            rowKey={(row) => `${row.kind}:${row.program}`}
            caption="AWS's recommendations, in the same term and payment option"
          />
        ) : null}
      </StateBoundary>
    </section>
  );
}
