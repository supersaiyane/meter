import { expect, test, type Page } from '@playwright/test';

/**
 * The assistant, end to end. TASK-P7-011.
 *
 * A question typed, sent, and answered, and every value in the answer followed back to the
 * call it was read from by the links a reader would click. Asserted here and not only in the
 * unit tests because this is about the built bundle: the route resolves, the question leaves
 * in the body of a POST rather than in a URL, and the citations survive the build as links
 * that land somewhere.
 *
 * Routes are stubbed at the network boundary for the reason `cost.spec.ts` gives. The model is
 * not run: what is proven is what the screen does with an exchange the API sent.
 */

const QUESTION = 'What did we spend last month, and which service cost the most?';
const AS_OF = '2026-10-03T04:00:00Z';

/** Meter's own work has no as_of, so the API sends none and computes degraded. */
function ownWork(unit: string) {
  return {
    as_of: null,
    collected_at: null,
    scope_coverage: { visible: 0, total: 0, is_partial: false, unit },
    degraded: true,
    failures: [],
  };
}

const ANSWERED = {
  data: {
    exchange_id: '7a1c0f3e-0001-4000-8000-000000000001',
    question: QUESTION,
    outcome: 'ANSWERED',
    answer: {
      prose:
        'The latest billing period cost {{total}}, and the largest service was {{service}}.',
      citations: [
        {
          placeholder: 'total',
          tool: 'get_cost_summary',
          call_id: 'toolu_cost_summary',
          field: 'data.current.effective_cost',
          value: '3781.9335',
          kind: 'figure',
          provenance: 'measured',
          as_of: AS_OF,
        },
        {
          placeholder: 'service',
          tool: 'get_cost_by_service',
          call_id: 'toolu_by_service',
          field: 'data[name=AmazonEC2].name',
          value: 'AmazonEC2',
          kind: 'label',
          provenance: 'measured',
          as_of: AS_OF,
        },
      ],
    },
    refusal: null,
    failure: null,
    tool_calls: [
      { call_id: 'toolu_cost_summary', tool: 'get_cost_summary', returned: true },
      { call_id: 'toolu_by_service', tool: 'get_cost_by_service', returned: true },
    ],
    model_id: 'anthropic.claude-sonnet-4-5-v1',
    input_tokens: 4210,
    output_tokens: 286,
    est_cost: '0.0169200000',
    asked_at: '2026-10-04T08:12:00Z',
    answered_at: '2026-10-04T08:12:09Z',
  },
  meta: {
    as_of: AS_OF,
    collected_at: '2026-10-04T08:12:09Z',
    scope_coverage: { visible: 1, total: 1, is_partial: false, unit: 'exchanges' },
    degraded: false,
    failures: [],
  },
};

interface Sent {
  readonly method: string;
  readonly url: string;
  readonly body: unknown;
}

async function withSession(page: Page): Promise<Sent[]> {
  await page.addInitScript(() => {
    window.localStorage.setItem('meter.token', 'a-session-token');
  });

  await page.route('**/api/v1/assistant/exchanges', async (route) => {
    await route.fulfill({ json: { data: [], meta: ownWork('exchanges') } });
  });
  await page.route('**/api/v1/assistant/redactions', async (route) => {
    await route.fulfill({ json: { data: [], meta: ownWork('redactions') } });
  });

  const sent: Sent[] = [];
  await page.route('**/api/v1/assistant/ask', async (route) => {
    const request = route.request();
    sent.push({ method: request.method(), url: request.url(), body: request.postDataJSON() });
    await route.fulfill({ json: ANSWERED });
  });
  return sent;
}

test('a question is answered, and every value in it leads back to the call it was read from', async ({
  page,
}) => {
  const sent = await withSession(page);
  await page.goto('/assistant');
  await expect(page.getByTestId('not-built')).toHaveCount(0);
  // The envelopes carry no as_of, so the strip says where freshness is rather than a date.
  await expect(page.getByTestId('global-freshness')).toHaveAttribute(
    'data-state',
    'per-figure',
  );
  await expect(page.getByTestId('global-freshness')).toHaveText(
    'Each citation carries its own as of date',
  );

  await page.getByLabel('Your question').fill(QUESTION);
  await page.getByRole('button', { name: 'Ask', exact: true }).click();

  const latest = page.getByTestId('assistant-latest');
  const prose = latest.getByTestId('cited-prose');
  await expect(prose).toContainText('$3,781.93');
  await expect(prose).toContainText('AmazonEC2');
  await expect(prose).not.toContainText('{{');
  await expect(prose.getByTestId('figure')).toHaveAttribute('data-provenance', 'measured');

  // In the body of a POST, never in the URL, where every access log on the way would keep it.
  expect(sent).toHaveLength(1);
  expect(sent[0]?.method).toBe('POST');
  expect(sent[0]?.body).toEqual({ question: QUESTION });
  expect(sent[0]?.url).not.toContain('spend');

  // The marker lands on its citation, which names the tool, the call, the field and as_of.
  await prose.getByRole('link', { name: 'Citation 1' }).click();
  const cited = latest.locator('[data-testid="citation"]:target');
  await expect(cited.getByTestId('citation-tool')).toHaveText('get_cost_summary');
  await expect(cited.getByTestId('citation-field')).toHaveText('data.current.effective_cost');
  await expect(cited.getByTestId('citation-as-of')).toHaveText('2026-10-03 04:00 UTC');

  // And the citation's call lands on the call the exchange made.
  await cited.getByRole('link', { name: 'toolu_cost_summary' }).click();
  const call = latest.locator('[data-testid="tool-call"]:target');
  await expect(call.getByTestId('tool-call-tool')).toHaveText('get_cost_summary');
  await expect(call).toHaveAttribute('data-returned', 'true');

  // What it cost, on the page: tokens measured, the cost modelled.
  await expect(latest.getByTestId('exchange-input-tokens')).toContainText('4,210 measured');
  await expect(latest.getByTestId('exchange-cost')).toContainText('~ $0.02 modelled');
});
