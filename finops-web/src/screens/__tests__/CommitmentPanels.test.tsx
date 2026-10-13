import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import { ApiError, type ApiClient } from '../../api/client';
import { costCommitmentsFixture } from '../../api/fixtures/cost';
import type { ApiPlanStatus, ApiPurchasePlan, ApiPurchasePlans } from '../../api/types';
import { CostCommitmentsScreen } from '../CostCommitmentsScreen';
import { PlanActions } from '../PlanActions';
import { Harness } from './Harness';
import { clientReturning, metaOf, posted, postedBodies } from './fixtures';

/**
 * The commitments screen's P14 panels, TASK-P14-009: the savings rate first, then what the payer
 * holds, when it ends, and Meter's plan beside AWS's, with the steps a payer may take.
 */

const PLAN_ID = 'plan-1';
const PLANS = '/api/v1/commitments/plans';

const me = (isGlobal: boolean) => ({
  data: {
    principal_id: 'p-1',
    display_name: 'Owner',
    tenant_id: 't-1',
    tiers: ['finops'],
    is_global: isGlobal,
    accounts_in_scope: 5,
  },
  meta: metaOf(),
});

const savingsRate = {
  data: {
    months: [
      {
        period: '2026-09-01',
        effective_cost: '800.00',
        list_cost: '1000.00',
        rate: '0.2000',
        rate_basis: 'measured' as const,
        lines: 120,
        lines_without_list_cost: 0,
        effective_cost_without_list_cost: '0',
        reason: null,
      },
      {
        period: '2026-10-01',
        effective_cost: '0',
        list_cost: '0',
        rate: null,
        rate_basis: 'measured' as const,
        lines: 40,
        lines_without_list_cost: 40,
        effective_cost_without_list_cost: '310.00',
        reason: 'No usage line this month carries a List Cost',
      },
    ],
  },
  meta: metaOf(),
};

const inventory = {
  data: {
    commitments: [
      {
        kind: 'savings_plan' as const,
        commitment_id: 'sp-fake-compute-0001',
        program: 'Compute',
        account_id: 'fake-platform-a',
        region_id: null,
        applies_to: null,
        quantity: null,
        hourly_commitment: '3.2000',
        term_months: 12,
        payment_option: 'No Upfront',
        upfront_amount: '0',
        recurring_hourly: '3.2000',
        currency: 'USD',
        starts_at: '2025-11-03T00:00:00Z',
        ends_at: '2026-11-03T00:00:00Z',
        state: 'active',
      },
      {
        kind: 'savings_plan' as const,
        commitment_id: 'sp-fake-ec2-0001',
        program: 'EC2Instance',
        account_id: 'fake-platform-a',
        region_id: 'us-fake-1',
        applies_to: 'm5',
        quantity: null,
        hourly_commitment: '1.1000',
        term_months: 36,
        payment_option: 'Partial Upfront',
        upfront_amount: '14454.00',
        recurring_hourly: '0.5500',
        currency: 'USD',
        starts_at: '2025-09-07T00:00:00Z',
        ends_at: '2028-09-07T00:00:00Z',
        state: 'active',
      },
    ],
    unreadable: ['DynamoDB'],
  },
  meta: metaOf(),
};

const calendar = {
  data: {
    months: [
      {
        month: '2026-11-01',
        commitments: ['sp-fake-compute-0001'],
        hourly_value: '3.2000',
        share: '0.6400',
        basis: 'measured' as const,
        over_limit: true,
      },
      {
        month: '2026-12-01',
        commitments: [],
        hourly_value: '0',
        share: '0',
        basis: 'measured' as const,
        over_limit: false,
      },
    ],
    ladder_limit: '0.0833',
    total_hourly_value: '5.0000',
    total_basis: 'modelled' as const,
  },
  meta: metaOf(),
};

function plans(status: ApiPlanStatus = 'DRAFT'): {
  data: ApiPurchasePlans;
  meta: ReturnType<typeof metaOf>;
} {
  const line = (lineNo: number, tranche: string) => ({
    line_no: lineNo,
    program: 'EC2Instance',
    instance_family: 'm6i',
    region_id: 'us-fake-1',
    tranche_month: tranche,
    hourly_commitment: '0.039',
    discount_percent: '40.0000',
    covers_hourly: '0.0650',
    monthly_saving: '18.98',
    usage_floor_percent: '60.0',
    upfront_cost: '0.00',
    matched_commitment_id: null,
    basis: 'modelled' as const,
  });
  return {
    data: {
      plan: {
        plan_id: PLAN_ID,
        plan_month: '2026-10-01',
        status,
        target_coverage: '0.800',
        term_years: 1,
        payment_option: 'No Upfront',
        ladder_limit: '0.0833',
        window_start: '2026-09-13',
        window_end: '2026-10-13',
        days_held: 30,
        steady_hourly: '1.0000',
        held_hourly: '0.0000',
        target_hourly: '0.4800',
        beyond_hourly: '0.0120',
        no_purchase_reason: null,
        currency: 'USD',
        unpriced: [
          {
            instance_family: 'g5',
            region_id: 'us-fake-1',
            steady_hourly: '1.0060',
            reason: 'P9 holds no Savings Plans rate for this family in this Region',
          },
        ],
        as_of: '2026-10-12T00:00:00Z',
        collected_at: '2026-10-13T06:00:00Z',
      },
      no_plan_reason: null,
      lines: [line(1, '2026-10-01'), line(2, '2026-11-01')],
      provider: [
        {
          kind: 'savings_plan',
          program: 'Compute',
          term_years: 1,
          payment_option: 'No Upfront',
          lookback_days: 30,
          recommended: true,
          hourly_commitment: '0.850',
          units: null,
          estimated_monthly_savings: '142.35',
          estimated_savings_percent: '21.4',
          upfront_cost: '0',
          currency: 'USD',
          failure_cause: null,
          failure_detail: null,
          as_of: '2026-10-12T00:00:00Z',
          collected_at: '2026-10-13T06:00:00Z',
        },
        {
          kind: 'reservation',
          program: 'Amazon Relational Database Service',
          term_years: 1,
          payment_option: 'No Upfront',
          lookback_days: 30,
          recommended: true,
          hourly_commitment: null,
          units: '2.0000',
          estimated_monthly_savings: '54.20',
          estimated_savings_percent: '28.5',
          upfront_cost: '0',
          currency: 'USD',
          failure_cause: null,
          failure_detail: null,
          as_of: '2026-10-12T00:00:00Z',
          collected_at: '2026-10-13T06:00:00Z',
        },
        {
          kind: 'reservation',
          program: 'Amazon Redshift',
          term_years: 1,
          payment_option: 'No Upfront',
          lookback_days: 0,
          recommended: null,
          hourly_commitment: null,
          units: null,
          estimated_monthly_savings: null,
          estimated_savings_percent: null,
          upfront_cost: null,
          currency: null,
          failure_cause: 'Throttled',
          failure_detail: 'Throttled in purchase_recommendation',
          as_of: '2026-10-13T06:00:00Z',
          collected_at: '2026-10-13T06:00:00Z',
        },
      ],
      difference: [
        "Meter's plan is drawn from the tenth percentile of the 30 days the bill holds of the last 30, so a quiet day sets it; the provider looked back 30 days and does not say which day set its figure.",
      ],
      events: [
        {
          from_status: null,
          to_status: 'DRAFT',
          principal: 'collector:purchase_plan',
          at: '2026-10-13T06:00:00Z',
          note: 'Drafted.',
        },
      ],
    },
    meta: metaOf(),
  };
}

function planOf(found: ApiPurchasePlans): ApiPurchasePlan {
  if (found.plan === null) {
    throw new Error('the fixture always holds a plan');
  }
  return found.plan;
}

function answers(isGlobal = true) {
  return {
    '/api/v1/cost/commitments': costCommitmentsFixture(),
    '/api/v1/me': me(isGlobal),
    '/api/v1/commitments/savings-rate?months=12': savingsRate,
    '/api/v1/commitments/inventory': inventory,
    '/api/v1/commitments/calendar': calendar,
    [PLANS]: plans(),
    [`${PLANS}/${PLAN_ID}/approve`]: plans('APPROVED'),
  };
}

function renderScreen(client: ApiClient = clientReturning(answers())) {
  return render(
    <Harness client={client}>
      <CostCommitmentsScreen />
    </Harness>,
  );
}

describe('CostCommitmentsScreen, P14', () => {
  beforeEach(() => {
    posted.length = 0;
    postedBodies.length = 0;
  });

  it('opens on the effective savings rate, and a month with no List Cost says so', async () => {
    renderScreen();
    const headline = await screen.findByTestId('savings-rate-headline');
    expect(headline).toHaveTextContent('October 2026');
    expect(headline).toHaveTextContent('No usage line this month carries a List Cost');
    const first = screen.getByTestId('savings-rate');
    const note = screen.getByTestId('commitment-scope-note');
    // The rate comes before everything else the screen says.
    expect(first.compareDocumentPosition(note) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('shows the payer what it holds and flags a month above the ladder', async () => {
    renderScreen();
    const held = await screen.findByTestId('commitment-inventory');
    expect(await within(held).findByText('sp-fake-compute-0001')).toBeInTheDocument();
    expect(within(held).getByText('EC2 Instance Savings Plan')).toBeInTheDocument();
    expect(screen.getByTestId('commitment-unreadable')).toHaveTextContent(
      'DynamoDB reserved capacity has no API to read',
    );
    expect(await screen.findByTestId('over-limit-2026-11-01')).toHaveTextContent(
      'Above the 8.33 percent limit',
    );
  });

  it("shows Meter's plan beside AWS's, a failure as its cause and a gap as unpriced", async () => {
    renderScreen();
    expect(await screen.findByTestId('plan-heading')).toHaveTextContent(
      "Meter's plan for October 2026: Draft",
    );
    expect(screen.getByTestId('plan-difference')).toHaveTextContent('looked back 30 days');
    expect(screen.getByTestId('plan-unpriced')).toHaveTextContent('not counted as nothing');
    const plansPanel = screen.getByTestId('purchase-plans');
    expect(within(plansPanel).getByText('Could not be read: Throttled')).toBeInTheDocument();
    expect(within(plansPanel).getByText('October 2026, to buy now')).toBeInTheDocument();
    // ISS-298: the API's column places are not the reader's.
    expect(within(plansPanel).getByText('2 instances or nodes')).toBeInTheDocument();
    expect(screen.getByTestId('plan-unpriced')).toHaveTextContent('1.006 USD an hour');
  });

  it('offers approve to a payer once a note is written, and records it', async () => {
    const user = userEvent.setup();
    renderScreen();
    const approve = await screen.findByRole('button', { name: "Approve this month's tranche" });
    expect(approve).toBeDisabled();
    await user.type(screen.getByLabelText('Why, for the record'), 'Within the ladder');
    expect(approve).toBeEnabled();
    await user.click(approve);
    expect(posted).toContain(`${PLANS}/${PLAN_ID}/approve`);
    expect(postedBodies.at(-1)).toEqual({ note: 'Within the ladder' });
  });

  it("shows a refusal in the API's own words", async () => {
    const user = userEvent.setup();
    const base = clientReturning(answers());
    const refusing: ApiClient = {
      ...base,
      post: () =>
        Promise.reject(
          new ApiError(
            409,
            JSON.stringify({ detail: 'This plan is approved, so it cannot be approved.' }),
          ),
        ),
    };
    renderScreen(refusing);
    await user.type(await screen.findByLabelText('Why, for the record'), 'Within the ladder');
    await user.click(screen.getByRole('button', { name: 'Withdraw' }));
    expect(await screen.findByTestId('plan-step-refused')).toHaveTextContent(
      'This plan is approved, so it cannot be approved.',
    );
  });

  it('tells a narrowed reader why the payer panels are not shown', async () => {
    renderScreen(clientReturning(answers(false)));
    expect(await screen.findByTestId('commitment-payer-only')).toHaveTextContent(
      'whole organization',
    );
    expect(screen.queryByTestId('purchase-plans')).toBeNull();
  });
});

describe('PlanActions', () => {
  const plan = (status: ApiPlanStatus) => planOf(plans(status).data);

  function renderActions(status: ApiPlanStatus, mayAct = true, buysThisMonth = true) {
    return render(
      <Harness client={clientReturning({})}>
        <PlanActions plan={plan(status)} mayAct={mayAct} buysThisMonth={buysThisMonth} />
      </Harness>,
    );
  }

  it('says why to a reader who may not take a step', () => {
    renderActions('DRAFT', false);
    expect(screen.getByTestId('plan-actions-refused')).toHaveTextContent('bought by the payer');
  });

  it('offers recording a purchase only once approved, and says Meter does not buy', () => {
    renderActions('APPROVED');
    expect(screen.getByRole('button', { name: 'Record as bought' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: "Approve this month's tranche" })).toBeNull();
    expect(screen.getByTestId('plan-buy-note')).toHaveTextContent('Meter does not buy');
  });

  it.each([
    ['BOUGHT', 'not yet seen stays bought'],
    ['VERIFIED', 'every line it bought'],
    ['WITHDRAWN', 'drafted afresh'],
    ['LAPSED', 'nobody approved it'],
  ] as const)('says what is settled about a %s plan', (status, says) => {
    renderActions(status);
    expect(screen.getByTestId('plan-actions-settled')).toHaveTextContent(says);
  });

  it('does not offer approval of a plan that buys nothing this month', () => {
    renderActions('DRAFT', true, false);
    expect(screen.queryByRole('button', { name: "Approve this month's tranche" })).toBeNull();
    expect(screen.getByRole('button', { name: 'Withdraw' })).toBeInTheDocument();
  });
});
