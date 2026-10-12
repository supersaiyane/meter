import type {
  ApiAiCallers,
  ApiAiGpuFleet,
  ApiAiGrouping,
  ApiAiSpend,
  ApiAiSpendRow,
  ApiEnvelope,
  ApiMeta,
} from '../types';

/**
 * The P13 surfaces, offline. FEAT-081 to FEAT-085.
 *
 * The routes are live, so `resolveSurface` never reaches these. They are the typed example the
 * screen's own tests render, which keeps those tests from inventing a shape the routes cannot
 * produce.
 *
 * **Deliberately unflattering, the way an estate is.** The cloud bill counts its own tokens and a
 * provider's come from its usage report, so one row is measured and one modelled. One model's line
 * counted no tokens at all, one caller used a model the bill priced nothing for, and one GPU
 * instance's agent never published. A fixture where every figure was known would leave the half of
 * the screen that matters rendered by nothing.
 */

const AS_OF = '2026-10-12T06:00:00Z';
const COLLECTED_AT = '2026-10-12T06:20:00Z';
const PERIOD = '2026-09-01';

function meta(): ApiMeta {
  return {
    as_of: AS_OF,
    collected_at: COLLECTED_AT,
    scope_coverage: { visible: 3, total: 3, is_partial: false, unit: 'accounts' },
    degraded: false,
    failures: [],
  };
}

function row(overrides: Partial<ApiAiSpendRow> & Pick<ApiAiSpendRow, 'name'>): ApiAiSpendRow {
  return {
    provider: 'AWS',
    cost: '0',
    tokens: null,
    tokens_basis: null,
    requests: null,
    cost_per_1k_tokens: null,
    cost_per_1k_tokens_basis: null,
    cost_per_request: null,
    cost_per_request_basis: null,
    ...overrides,
  };
}

/** Each grouping's rows, worst first, as the route orders them. */
const ROWS: Readonly<Record<ApiAiGrouping, readonly ApiAiSpendRow[]>> = {
  provider: [
    row({
      name: 'AWS',
      cost: '1840.250000',
      tokens: '412000000',
      tokens_basis: 'measured',
      requests: 96000,
      cost_per_1k_tokens: '0.004467',
      cost_per_1k_tokens_basis: 'measured',
      cost_per_request: '0.019169',
      cost_per_request_basis: 'modelled',
    }),
    row({
      name: 'OpenAI',
      provider: 'OpenAI',
      cost: '615.400000',
      tokens: '88000000',
      tokens_basis: 'modelled',
      requests: 41000,
      cost_per_1k_tokens: '0.006993',
      cost_per_1k_tokens_basis: 'modelled',
      cost_per_request: '0.015010',
      cost_per_request_basis: 'modelled',
    }),
  ],
  model: [
    row({
      name: 'ClaudeSonnet4',
      cost: '1612.000000',
      tokens: '380000000',
      tokens_basis: 'measured',
      requests: 90000,
      cost_per_1k_tokens: '0.004242',
      cost_per_1k_tokens_basis: 'measured',
      cost_per_request: '0.017911',
      cost_per_request_basis: 'modelled',
    }),
    row({
      name: 'gpt-4o-2024-08-06',
      provider: 'OpenAI',
      cost: '615.400000',
      tokens: '88000000',
      tokens_basis: 'modelled',
      requests: 41000,
      cost_per_1k_tokens: '0.006993',
      cost_per_1k_tokens_basis: 'modelled',
      cost_per_request: '0.015010',
      cost_per_request_basis: 'modelled',
    }),
    // A line the bill filed under AI that counted no tokens: an unknown, never nought.
    row({ name: 'NovaCanvas', cost: '228.250000' }),
  ],
  token_type: [
    row({
      name: 'output',
      provider: '(several)',
      cost: '1490.650000',
      tokens: '96000000',
      tokens_basis: 'measured',
      cost_per_1k_tokens: '0.015528',
      cost_per_1k_tokens_basis: 'measured',
    }),
    row({
      name: 'input',
      provider: '(several)',
      cost: '965.000000',
      tokens: '404000000',
      tokens_basis: 'measured',
      cost_per_1k_tokens: '0.002389',
      cost_per_1k_tokens_basis: 'measured',
    }),
  ],
  feature: [
    row({ name: 'support-bot', cost: '1290.000000', requests: 70000 }),
    row({ name: 'not named', provider: '(several)', cost: '1165.650000' }),
  ],
  caller: [
    row({
      name: 'arn:aws:sts::111122223333:assumed-role/support/triage',
      cost: '1290.000000',
      requests: 70000,
      cost_per_request: '0.018429',
      cost_per_request_basis: 'modelled',
    }),
    row({ name: 'not named', provider: '(several)', cost: '1165.650000' }),
  ],
};

export function aiSpendFixture(groupBy: ApiAiGrouping = 'provider'): ApiEnvelope<ApiAiSpend> {
  const rows = ROWS[groupBy];
  const total = rows.reduce((sum, one) => sum + Number(one.cost), 0);
  return {
    data: {
      period: PERIOD,
      group_by: groupBy,
      total_cost: total.toFixed(6),
      rows,
      connected: [
        { provider: 'openai', organization_id: 'org-fake-openai', name: 'Fake OpenAI' },
      ],
    },
    meta: meta(),
  };
}

/** No AI line in any bill this reader can see: a period of null, never a total of nought. */
export function aiSpendNoneFixture(): ApiEnvelope<ApiAiSpend> {
  return {
    data: { period: null, group_by: 'provider', total_cost: null, rows: [], connected: [] },
    meta: { ...meta(), as_of: null, collected_at: null },
  };
}

export function aiCallersFixture(): ApiEnvelope<ApiAiCallers> {
  return {
    data: {
      period: PERIOD,
      callers: [
        {
          source: 'logs',
          account_id: '111122223333',
          caller: 'arn:aws:sts::111122223333:assumed-role/support/triage',
          application: 'support',
          model: 'publisher.claude-sonnet-4-20250514-v1:0',
          tokens: 300000000,
          requests: 70000,
          modelled_cost: '1290.000000',
          modelled_cost_basis: 'modelled',
        },
        {
          source: 'openai',
          account_id: 'org-fake-openai',
          caller: 'user-fake-analyst',
          application: 'proj-research',
          model: 'gpt-4o-2024-08-06',
          tokens: 88000000,
          requests: null,
          modelled_cost: '615.400000',
          modelled_cost_basis: 'modelled',
        },
        // A model the bill priced none of: unknown, never free.
        {
          source: 'logs',
          account_id: '111122223333',
          caller: 'arn:aws:sts::111122223333:assumed-role/batch/nightly',
          application: '',
          model: 'publisher.embed-v4:0',
          tokens: 1200000,
          requests: 400,
          modelled_cost: null,
          modelled_cost_basis: 'modelled',
        },
      ],
    },
    meta: meta(),
  };
}

export function aiGpuFixture(): ApiEnvelope<ApiAiGpuFleet> {
  return {
    data: {
      period: PERIOD,
      instances: [
        {
          account_id: '111122223333',
          region_id: 'eu-west-1',
          instance_id: 'i-0fakegpu0002',
          instance_type: 'p4d.24xlarge',
          hours: '720',
          cost: '23593.680000',
          days_billed: 30,
          days_published: 0,
          average_percent: null,
          peak_percent: null,
          utilization: 'not published',
        },
        {
          account_id: '111122223333',
          region_id: 'eu-west-1',
          instance_id: 'i-0fakegpu0001',
          instance_type: 'g5.xlarge',
          hours: '720',
          cost: '724.320000',
          days_billed: 30,
          days_published: 12,
          average_percent: '18.50',
          peak_percent: '71.00',
          utilization: 'partly published',
        },
        {
          account_id: '444455556666',
          region_id: 'us-east-1',
          instance_id: 'i-0fakegpu0003',
          instance_type: 'g6.2xlarge',
          hours: '240',
          cost: '233.760000',
          days_billed: 10,
          days_published: 10,
          average_percent: '64.25',
          peak_percent: '97.00',
          utilization: 'published',
        },
      ],
    },
    meta: meta(),
  };
}
