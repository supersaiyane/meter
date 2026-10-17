import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import type { ApiClient } from '../../api/client';
import type {
  ApiEstimateAccuracy,
  ApiEstimateAccuracyRow,
  ApiEstimateComparison,
  ApiEstimates,
  ApiPlanEstimate,
  ApiPlanEstimateDetail,
} from '../../api/types';
import { EstimatesScreen } from '../EstimatesScreen';
import {
  accuracySentence,
  actionsName,
  unpricedSentence,
  verdictSentence,
} from '../estimatesModel';
import { Harness } from './Harness';
import { clientReturning, metaOf } from './fixtures';

/**
 * The Estimates screen, TASK-P16-008: each plan with the unpriced count first, one plan's lines
 * with why a change is not priced and what the bill said, and the accuracy from the judged alone.
 * The organization's only, ADR-0025: anyone else is told why and nothing is read.
 */

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

const PLAN: ApiPlanEstimate = {
  plan_id: 'plan-1',
  repository: 'acme/infra',
  pull_request: 7,
  head_sha: 'abc1234def0000',
  folder: 'storage',
  status: 'PRICED',
  reason: null,
  received_at: '2026-10-16T09:00:00Z',
  monthly_before: '0.000000',
  monthly_after: '82.510000',
  monthly_change: '82.510000',
  currency: 'USD',
  priced_lines: 2,
  unpriced_lines: 1,
  comment_status: 'WRITTEN',
  comment_url: 'https://code.example/acme/infra/pull/7#issuecomment-1',
  comment_reason: null,
  pull_request_state: 'MERGED',
  as_of: '2026-10-16T09:00:00Z',
  collected_at: '2026-10-16T09:10:00Z',
  basis: 'modelled',
};

const REFUSED: ApiPlanEstimate = {
  ...PLAN,
  plan_id: 'plan-2',
  pull_request: 8,
  folder: '',
  status: 'REFUSED',
  reason: 'the plan is not JSON from terraform show',
  monthly_before: null,
  monthly_after: null,
  monthly_change: null,
  currency: null,
  priced_lines: null,
  unpriced_lines: null,
  comment_status: null,
  comment_url: null,
  pull_request_state: null,
};

const COMPARED: ApiEstimateComparison = {
  verdict: 'WITHIN',
  reason: null,
  provider_id: 'i-0123456789abcdef0',
  window_start: '2026-10-12',
  window_end: '2026-11-11',
  list_monthly: '80.300000',
  effective_monthly: '58.400000',
  variance_percent: '10.0000',
  as_of: '2026-11-11T08:00:00Z',
  basis: 'measured',
};

const DETAIL: ApiPlanEstimateDetail = {
  plan: PLAN,
  lines: [
    {
      address: 'aws_nat_gateway.out',
      resource_type: 'aws_nat_gateway',
      actions: ['create'],
      region: 'eu-west-1',
      monthly_before: null,
      monthly_after: null,
      reason: 'usage based: priced by the data it carries, which a plan does not say',
      notes: [],
      unknown: [],
      withheld: [],
      components: [],
      comparison: null,
      basis: 'modelled',
    },
    {
      address: 'aws_instance.web',
      resource_type: 'aws_instance',
      actions: ['create'],
      region: 'eu-west-1',
      monthly_before: null,
      monthly_after: '73.000000',
      reason: null,
      notes: ['priced as Linux'],
      unknown: ['ami'],
      withheld: [],
      components: [
        {
          side: 'after',
          what: 'm7g.large, Linux, shared tenancy',
          quantity: '730',
          unit: 'Hrs',
          unit_price: '0.1000000000',
          monthly: '73.000000',
          sku_price_id: 'sku-1',
          version: '20261001',
          basis: 'modelled',
        },
      ],
      comparison: COMPARED,
      basis: 'modelled',
    },
  ],
  assumptions:
    "Modelled from AWS's on demand list prices, 730 hours a month, in USD, at the price list version each component names.",
};

const EVERY_TYPE: ApiEstimateAccuracyRow = {
  resource_type: 'all',
  compared: 2,
  within: 1,
  median_error_percent: '11.0000',
  basis: 'modelled against measured',
};

const ACCURACY: ApiEstimateAccuracy = {
  types: [{ ...EVERY_TYPE, resource_type: 'aws_instance' }, EVERY_TYPE],
  within_percent: '10',
  window_days: 30,
  pending: 3,
  not_compared: 1,
};

function answers(isGlobal = true) {
  const plans: ApiEstimates = { plans: [PLAN, REFUSED], more: false };
  return {
    '/api/v1/me': me(isGlobal),
    '/api/v1/estimates': { data: plans, meta: metaOf() },
    '/api/v1/estimates/plan-1': { data: DETAIL, meta: metaOf() },
    '/api/v1/estimates/accuracy': { data: ACCURACY, meta: metaOf() },
  };
}

function renderScreen(client: ApiClient = clientReturning(answers())) {
  return render(
    <Harness client={client}>
      <EstimatesScreen />
    </Harness>,
  );
}

describe('EstimatesScreen', () => {
  it('lists each plan with the unpriced count first, and says why one was refused', async () => {
    renderScreen();
    const plans = await screen.findByTestId('estimate-plans');
    const cells = await within(plans).findAllByTestId('plan-unpriced');
    expect(cells[0]).toHaveTextContent('1 of 3 resources is not priced');
    expect(cells[1]).toHaveTextContent('Refused: the plan is not JSON from terraform show');
    expect(within(plans).getByText('acme/infra#7, storage')).toBeInTheDocument();
    expect(within(plans).getByRole('link', { name: 'On the pull request' })).toHaveAttribute(
      'href',
      PLAN.comment_url,
    );
    // A refused plan has no lines to open.
    expect(within(plans).queryByTestId('open-plan-plan-2')).toBeNull();
  });

  it('opens a plan on its unpriced change, why, its parts, and what the bill said', async () => {
    renderScreen();
    await userEvent.click(await screen.findByTestId('open-plan-plan-1'));
    const lines = await screen.findByTestId('estimate-lines');
    expect(await within(lines).findByTestId('estimate-lines-headline')).toHaveTextContent(
      '1 of 2 resources is not priced',
    );
    const why = await within(lines).findAllByTestId('line-why');
    expect(why[0]).toHaveTextContent('usage based');
    expect(why[1]).toHaveTextContent('priced as Linux. Unknown until apply: ami');
    expect(within(lines).getAllByTestId('line-bill')[1]).toHaveTextContent(
      'Within 10 percent of the bill',
    );
    expect(within(lines).getByTestId('estimate-assumptions')).toHaveTextContent('730 hours');
  });

  it('heads the accuracy with the judged alone and counts the rest apart', async () => {
    renderScreen();
    expect(await screen.findByTestId('estimate-accuracy-waiting')).toHaveTextContent(
      '3 waiting for their 30 billed days, and 1 that cannot be compared',
    );
    expect(screen.getByTestId('estimate-accuracy-headline')).toHaveTextContent(
      '1 of 2 estimates came within 10 percent of the bill. The median error was 11 percent.',
    );
  });

  it('tells a narrowed reader why and reads nothing of the organization', async () => {
    renderScreen(clientReturning({ '/api/v1/me': me(false) }));
    expect(await screen.findByTestId('estimates-organization-only')).toHaveTextContent(
      'A plan names no account until it is applied',
    );
    expect(screen.queryByTestId('estimate-plans')).toBeNull();
  });
});

describe('estimatesModel', () => {
  it("counts the unpriced first, in the comment's grammar", () => {
    expect(unpricedSentence(1, 3)).toBe('1 of 3 resources is not priced');
    expect(unpricedSentence(2, 3)).toBe('2 of 3 resources are not priced');
    expect(unpricedSentence(1, 1)).toBe('1 of 1 resource is not priced');
    expect(unpricedSentence(0, 1)).toBe('The one resource is priced');
    expect(unpricedSentence(0, 4)).toBe('All 4 resources are priced');
    expect(unpricedSentence(0, 0)).toBe('No resource changes');
  });

  it('names a delete and a create together a replacement', () => {
    expect(actionsName(['delete', 'create'])).toBe('Replace');
    expect(actionsName(['update'])).toBe('Change');
    expect(actionsName(['delete'])).toBe('Destroy');
  });

  it('says each verdict in words, the window by its last day', () => {
    const verdict = (changed: Partial<ApiEstimateComparison>) =>
      verdictSentence({ ...COMPARED, ...changed }, '10');
    expect(verdict({ verdict: 'PENDING' })).toBe(
      'Waiting for the bill to reach 10 November 2026',
    );
    expect(verdict({ verdict: 'PENDING', window_end: null })).toBe(
      'Seen, waiting for its thirty billed days',
    );
    expect(verdict({ verdict: 'ABOVE', variance_percent: '27.2727' })).toBe(
      'The bill came in 27.3 percent above',
    );
    expect(verdict({ verdict: 'BELOW', variance_percent: '-30.0000' })).toBe(
      'The bill came in 30 percent below',
    );
    expect(verdict({ verdict: 'NOT_COMPARED', reason: 'no row for it' })).toBe(
      'Not compared: no row for it',
    );
  });

  it('says plainly when nothing has been compared yet', () => {
    const none = { ...EVERY_TYPE, compared: 0, within: 0, median_error_percent: null };
    expect(accuracySentence({ ...ACCURACY, types: [none] })).toMatch(
      /^No estimate has been set against the bill yet/,
    );
  });
});
