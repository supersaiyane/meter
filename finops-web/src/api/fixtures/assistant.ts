import type {
  ApiCitation,
  ApiDigest,
  ApiEnvelope,
  ApiExchange,
  ApiMeta,
  ApiRedaction,
} from '../types';

/**
 * The P7 surfaces, offline. FEAT-038, FEAT-041, FEAT-042 and FEAT-046.
 *
 * The routes are live, so `resolveSurface` never reaches these, as with the container
 * fixtures. They are the typed example the screens' own tests render, which keeps those tests
 * from inventing a shape the routes cannot produce.
 *
 * **One of each outcome, and the unflattering ones on purpose.** An answer whose every value
 * is cited, with a modelled figure among the measured ones and a tool call that never
 * returned. A refusal that names the screen that would answer it and one that cannot, because
 * the question held a credential. A throttled failure. And the failure a deployment without a
 * model gives every question, which is the normal state until OPEN-10 is answered.
 *
 * The digests are one of each state as well: composed and kept, which is every digest until
 * OPEN-11 names a sender, beside one marked sent so the other half of the screen is rendered
 * by something.
 */

const COST_AS_OF = '2026-10-03T04:00:00Z';
const QUERY_AS_OF = '2026-10-02T06:00:00Z';
const WEEK_AS_OF = '2026-09-28T04:00:00Z';
const COMPOSED_AT = '2026-09-28T06:00:00Z';
const MODEL = 'anthropic.claude-sonnet-4-5-v1';

/** The detail `finops_api/assistant.py` stores when no model is configured. */
export const NOT_ENABLED =
  'No model is configured for the assistant in this deployment, so the question was sent ' +
  'nowhere. Choosing one is OPEN-10, and it is the setting METER_ASSISTANT_MODEL_ID.';

/** What `finops_ingest/collectors/digests.py` stores beside a digest nobody could send. */
export const UNSENT =
  'No sender is configured, so the digest was composed and kept here. Where a digest goes, ' +
  'email or Slack or both, is OPEN-11.';

/**
 * What the API tells a person who asked, for each typed cause. `REMEDIATION` in
 * `finops_api/routes/assistant.py`.
 *
 * Written for the assistant, so none of them says to re run a collector: somebody who asked a
 * question has none to re run. Keyed by the name the row stores the cause under.
 */
export const REMEDIATION = {
  AccessDenied:
    'The hub role may not invoke this model. Add it to assistant_model_ids in the hub stack, ' +
    'then ask again.',
  Throttled:
    'Too many questions are being answered at once, by Meter or by the model service. ' +
    'Ask again in a minute.',
  NotOptedIn:
    'Name a model in METER_ASSISTANT_MODEL_ID, enable access to it for the hub account, ' +
    'and grant it through assistant_model_ids in the hub stack.',
  NoData:
    'The tools returned nothing to answer from. Ask about a period or a scope that has been ' +
    'collected.',
  Unreachable:
    'The model service did not answer. Ask again, and if it keeps failing, check the ' +
    "service's health in the hub account's region.",
  SchemaDrift:
    'The answer could not be checked against the tool results, so it is not shown. Ask again, ' +
    'or ask a narrower question.',
  Misconfigured:
    'METER_ASSISTANT_MODEL_ID names a model the hub account is not offered. Correct the ' +
    'setting.',
} as const;

/**
 * The envelope the exchange and redaction lists carry.
 *
 * An exchange records Meter's own work, so it has no `as_of`, spec section 6.1, and the API
 * computes `degraded` as true whenever `as_of` is null. Mirrored rather than tidied, so a
 * screen tested against this meets the envelope it will actually receive.
 */
function ownWorkMeta(visible: number, total: number, unit: string): ApiMeta {
  return {
    as_of: null,
    collected_at: null,
    scope_coverage: { visible, total, is_partial: visible < total, unit },
    degraded: true,
    failures: [],
  };
}

/** A measured figure unless the case says otherwise, which is what most citations are. */
function cited(
  partial: Omit<ApiCitation, 'kind' | 'provenance'> & Partial<ApiCitation>,
): ApiCitation {
  return { kind: 'figure', provenance: 'measured', ...partial };
}

export function answeredExchange(): ApiExchange {
  return {
    exchange_id: '7a1c0f3e-0001-4000-8000-000000000001',
    question: 'What did we spend last month, and which service cost the most?',
    outcome: 'ANSWERED',
    answer: {
      prose:
        'The latest billing period cost {{total}} after discounts, against {{previous}} the ' +
        'period before. The largest service was {{service}}, at {{service_cost}}. The most ' +
        'expensive dashboard query is modelled at {{query_cost}} a month.',
      citations: [
        cited({
          placeholder: 'total',
          tool: 'get_cost_summary',
          call_id: 'toolu_cost_summary',
          field: 'data.current.effective_cost',
          value: '3781.9335',
          as_of: COST_AS_OF,
        }),
        cited({
          placeholder: 'previous',
          tool: 'get_cost_summary',
          call_id: 'toolu_cost_summary',
          field: 'data.previous.effective_cost',
          value: '6197.6500',
          as_of: COST_AS_OF,
        }),
        cited({
          placeholder: 'service',
          tool: 'get_cost_by_service',
          call_id: 'toolu_by_service',
          field: 'data[name=AmazonEC2].name',
          value: 'AmazonEC2',
          kind: 'label',
          as_of: COST_AS_OF,
        }),
        cited({
          placeholder: 'service_cost',
          tool: 'get_cost_by_service',
          call_id: 'toolu_by_service',
          field: 'data[name=AmazonEC2].effective_cost',
          value: '2043.1120',
          as_of: COST_AS_OF,
        }),
        cited({
          placeholder: 'query_cost',
          tool: 'list_expensive_queries',
          call_id: 'toolu_queries',
          field: 'data[finding_id=11111111-1111-1111-1111-111111111111].monthly_cost',
          value: '412.5000',
          provenance: 'modelled',
          as_of: QUERY_AS_OF,
        }),
      ],
    },
    refusal: null,
    failure: null,
    tool_calls: [
      { call_id: 'toolu_cost_summary', tool: 'get_cost_summary', returned: true },
      { call_id: 'toolu_by_service', tool: 'get_cost_by_service', returned: true },
      // Asked for and never answered. Listed, because a reader replaying the answer needs
      // to know the model tried, and nothing it would have said is in the prose.
      { call_id: 'toolu_freshness', tool: 'get_freshness', returned: false },
      { call_id: 'toolu_queries', tool: 'list_expensive_queries', returned: true },
    ],
    model_id: MODEL,
    input_tokens: 4210,
    output_tokens: 286,
    est_cost: '0.0169200000',
    asked_at: '2026-10-04T08:12:00Z',
    answered_at: '2026-10-04T08:12:09Z',
  };
}

/** The spec's own example: understood, and not answerable from what the product holds. */
export function refusedWithScreen(): ApiExchange {
  return {
    exchange_id: '7a1c0f3e-0002-4000-8000-000000000002',
    question: 'What did the payments cluster cost by workload last month?',
    outcome: 'REFUSED',
    answer: null,
    refusal: {
      gap: 'figure',
      reason:
        'get_container_cost has no workload breakdown for payments-eks, because split cost ' +
        'allocation data is not enabled for that account.',
      screen: '/cost/containers',
    },
    failure: null,
    tool_calls: [{ call_id: 'toolu_containers', tool: 'get_container_cost', returned: true }],
    model_id: MODEL,
    input_tokens: 3920,
    output_tokens: 140,
    est_cost: '0.0138600000',
    asked_at: '2026-10-04T07:40:00Z',
    answered_at: '2026-10-04T07:40:06Z',
  };
}

export function throttledExchange(): ApiExchange {
  return {
    exchange_id: '7a1c0f3e-0003-4000-8000-000000000003',
    question: 'How much did Meter itself cost this month?',
    outcome: 'FAILED',
    answer: null,
    refusal: null,
    failure: {
      cause: 'Throttled',
      detail: 'The model provider refused the call rate, so no answer was written.',
      remediation: REMEDIATION.Throttled,
    },
    tool_calls: [{ call_id: 'toolu_platform', tool: 'get_platform_cost', returned: true }],
    model_id: MODEL,
    input_tokens: 2100,
    output_tokens: 0,
    est_cost: '0.0063000000',
    asked_at: '2026-10-04T07:10:00Z',
    answered_at: '2026-10-04T07:10:31Z',
  };
}

/** Blocked before anything was sent. The question is kept with the credential removed. */
export function refusedSecret(): ApiExchange {
  return {
    exchange_id: '7a1c0f3e-0004-4000-8000-000000000004',
    question: 'Why does the key [redacted: aws-access-token] cost so much?',
    outcome: 'REFUSED',
    answer: null,
    refusal: {
      gap: 'secret',
      reason:
        'The question held what looks like a credential, by the rule aws-access-token, so it ' +
        'was sent nowhere and kept only with the credential removed. Treat that credential as ' +
        'exposed and rotate it.',
      screen: null,
    },
    failure: null,
    tool_calls: [],
    model_id: null,
    input_tokens: 0,
    output_tokens: 0,
    // How the API sends a NUMERIC(20, 10) zero: Decimal('0E-10') becomes this text.
    est_cost: '0E-10',
    asked_at: '2026-10-04T06:55:00Z',
    answered_at: '2026-10-04T06:55:00Z',
  };
}

/** The normal state of a deployment without a model. Not enabled, and not broken. */
export function notEnabledExchange(): ApiExchange {
  return {
    exchange_id: '7a1c0f3e-0005-4000-8000-000000000005',
    question: 'Which team spent the most last week?',
    outcome: 'FAILED',
    answer: null,
    refusal: null,
    failure: {
      cause: 'NotOptedIn',
      detail: NOT_ENABLED,
      remediation: REMEDIATION.NotOptedIn,
    },
    tool_calls: [],
    model_id: null,
    input_tokens: 0,
    output_tokens: 0,
    est_cost: '0E-10',
    asked_at: '2026-10-03T16:20:00Z',
    answered_at: '2026-10-03T16:20:00Z',
  };
}

/** The asker's own exchanges, newest first, as `GET /assistant/exchanges` sends them. */
export function exchangesFixture(): ApiEnvelope<ApiExchange[]> {
  const data = [
    answeredExchange(),
    refusedWithScreen(),
    throttledExchange(),
    refusedSecret(),
    notEnabledExchange(),
  ];
  return { data, meta: ownWorkMeta(data.length, data.length, 'exchanges') };
}

/**
 * One exchange as `POST /assistant/ask` returns it.
 *
 * As fresh as its stalest cited figure, collected when it was answered, and with no freshness
 * at all when nothing was cited. The same rule as `_meta` in `finops_api/routes/assistant.py`.
 */
export function askFixture(
  exchange: ApiExchange = answeredExchange(),
): ApiEnvelope<ApiExchange> {
  const stamps = (exchange.answer?.citations ?? []).map((citation) => citation.as_of).sort();
  const asOf = stamps[0] ?? null;
  return {
    data: exchange,
    meta: {
      as_of: asOf,
      collected_at: asOf === null ? null : exchange.answered_at,
      scope_coverage: { visible: 1, total: 1, is_partial: false, unit: 'exchanges' },
      degraded: asOf === null,
      failures: [],
    },
  };
}

/** The asker's own redaction events, as `GET /assistant/redactions` sends them. */
export function redactionsFixture(): ApiEnvelope<ApiRedaction[]> {
  const data: ApiRedaction[] = [
    {
      event_id: '5e0d1b2c-0001-4000-8000-000000000001',
      exchange_id: refusedSecret().exchange_id,
      rule_id: 'aws-access-token',
      action: 'BLOCKED',
      occurred_at: '2026-10-04T06:55:00Z',
    },
  ];
  return { data, meta: ownWorkMeta(data.length, data.length, 'redactions') };
}

/** The two citations every digest opens with, as `finops_query/digest.py` composes them. */
function weekCitations(reference: string, spend: string): ApiCitation[] {
  return [
    cited({
      placeholder: 'week_end',
      tool: 'cost_focus_daily',
      call_id: reference,
      field: "the week's last day",
      value: '2026-09-27',
      kind: 'label',
      as_of: WEEK_AS_OF,
    }),
    cited({
      placeholder: 'spend',
      tool: 'cost_focus_daily',
      call_id: reference,
      field: 'effective_cost summed over the week',
      value: spend,
      as_of: WEEK_AS_OF,
    }),
  ];
}

export function executiveDigest(): ApiDigest {
  const reference = 'executive:organization:2026-09-21';
  return {
    digest_id: '9d4e2f10-0001-4000-8000-000000000001',
    audience: 'executive',
    team: null,
    period_start: '2026-09-21',
    period_end: '2026-09-27',
    prose:
      'In the week to {{week_end}}, the organization spent {{spend}}, against {{previous}} ' +
      'the week before. The largest service was {{service}}, at {{service_spend}}.',
    citations: [
      ...weekCitations(reference, '27410.5500'),
      cited({
        placeholder: 'previous',
        tool: 'cost_focus_daily',
        call_id: reference,
        field: 'effective_cost summed over the week before',
        value: '25980.1200',
        as_of: WEEK_AS_OF,
      }),
      cited({
        placeholder: 'service',
        tool: 'cost_focus_daily',
        call_id: reference,
        field: 'service_name',
        value: 'AmazonEC2',
        kind: 'label',
        as_of: WEEK_AS_OF,
      }),
      cited({
        placeholder: 'service_spend',
        tool: 'cost_focus_daily',
        call_id: reference,
        field: 'effective_cost of that service over the week',
        value: '11240.0000',
        as_of: WEEK_AS_OF,
      }),
    ],
    composed_at: COMPOSED_AT,
    // No deployment can send one until OPEN-11 names a sender. Here so the sent half of the
    // screen has something to render.
    sent_at: '2026-09-28T06:05:00Z',
    unsent_reason: null,
  };
}

export function teamDigest(): ApiDigest {
  const reference = 'team:payments:2026-09-21';
  return {
    digest_id: '9d4e2f10-0002-4000-8000-000000000002',
    audience: 'team',
    team: 'payments',
    period_start: '2026-09-21',
    period_end: '2026-09-27',
    prose:
      'In the week to {{week_end}}, {{team}} spent {{spend}}, and nothing billed the week ' +
      'before is held to compare it with.',
    citations: [
      ...weekCitations(reference, '4120.7700'),
      cited({
        placeholder: 'team',
        tool: 'cost_focus_daily',
        call_id: reference,
        field: 'tags.team',
        value: 'payments',
        kind: 'label',
        as_of: WEEK_AS_OF,
      }),
    ],
    composed_at: COMPOSED_AT,
    sent_at: null,
    unsent_reason: UNSENT,
  };
}

/** The weekly digests, newest first, as `GET /assistant/digests` sends them. Payer wide. */
export function digestsFixture(): ApiEnvelope<ApiDigest[]> {
  return {
    data: [executiveDigest(), teamDigest()],
    meta: {
      as_of: WEEK_AS_OF,
      collected_at: COMPOSED_AT,
      scope_coverage: { visible: 1, total: 1, is_partial: false, unit: 'payer' },
      degraded: false,
      failures: [],
    },
  };
}
