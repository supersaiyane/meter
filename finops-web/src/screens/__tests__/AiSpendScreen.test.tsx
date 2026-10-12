import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { AiSpendScreen } from '../AiSpendScreen';
import { Harness } from './Harness';
import { clientReturning } from './fixtures';
import {
  aiCallersFixture,
  aiGpuFixture,
  aiSpendFixture,
  aiSpendNoneFixture,
} from '../../api/fixtures/ai';
import type { ApiEnvelope } from '../../api/types';
import { violationsIn } from '../../components/__tests__/axe';

/**
 * FEAT-085, TASK-P13-008. AI spend as a reader meets it.
 *
 * The failures guarded are the ones the spec names: a figure that does not say how it was arrived
 * at, a small unit price drawn as nought, and an absence, tokens nobody counted, a caller nobody
 * priced, a GPU whose agent never published, drawn as a number when it is a sentence.
 */

const SPEND = '/api/v1/ai/spend?group_by=';
const CALLERS = '/api/v1/ai/callers';
const GPU = '/api/v1/ai/gpu';

function answers(spend: ApiEnvelope<unknown> = aiSpendFixture()) {
  return {
    [`${SPEND}provider`]: spend,
    [`${SPEND}model`]: aiSpendFixture('model'),
    [CALLERS]: aiCallersFixture(),
    [GPU]: aiGpuFixture(),
  };
}

function renderScreen(path = '/analyze/ai', spend?: ApiEnvelope<unknown>, failure?: Error) {
  return render(
    <Harness client={clientReturning(answers(spend), failure)} initialPath={path}>
      <AiSpendScreen />
    </Harness>,
  );
}

/** The element a test expects, or a failure naming it, rather than an assertion that it exists. */
function present<T>(value: T | undefined, what: string): T {
  if (value === undefined) throw new Error(`expected ${what}`);
  return value;
}

async function spendRows() {
  const panel = await screen.findByTestId('ai-spend');
  return within(panel).findAllByTestId('ai-spend-row');
}

describe('AiSpendScreen, spend', () => {
  it('shows each provider, the bill measured and a usage report modelled', async () => {
    renderScreen();
    const rows = await spendRows();
    expect(rows).toHaveLength(aiSpendFixture().data.rows.length);
    const cloud = present(rows[0], 'the cloud row');
    const provider = present(rows[1], 'the provider row');
    // The bill counts its own tokens; a provider's come from its usage report.
    expect(
      within(cloud).getByTestId('ai-per-1k').querySelector('[data-provenance]'),
    ).toHaveAttribute('data-provenance', 'measured');
    expect(
      within(provider).getByTestId('ai-per-1k').querySelector('[data-provenance]'),
    ).toHaveAttribute('data-provenance', 'modelled');
  });

  it('names the provider once when the grouping is the provider', async () => {
    renderScreen();
    const panel = await screen.findByTestId('ai-spend');
    await within(panel).findAllByTestId('ai-spend-row');
    expect(within(panel).getAllByRole('columnheader', { name: /^provider/i })).toHaveLength(1);
  });

  it('draws a cost per thousand tokens past the cent, never as nought', async () => {
    renderScreen();
    const cloud = present((await spendRows())[0], 'the cloud row');
    expect(within(cloud).getByTestId('ai-per-1k').textContent).toContain('$0.004467');
  });

  it('labels every cost per request modelled', async () => {
    renderScreen();
    const rows = await spendRows();
    for (const row of rows) {
      const figure = within(row)
        .getByTestId('ai-per-request')
        .querySelector('[data-provenance]');
      expect(figure).toHaveAttribute('data-provenance', 'modelled');
    }
  });

  it('says a model line nothing counted tokens for, rather than drawing nought', async () => {
    renderScreen('/analyze/ai?group_by=model');
    const rows = await spendRows();
    const silent = present(
      rows.find((row) => row.textContent.includes('NovaCanvas')),
      'the silent row',
    );
    expect(within(silent).getByTestId('ai-per-1k').textContent).toBe('no tokens counted');
    expect(
      within(silent).getByTestId('ai-per-1k').querySelector('[data-testid="figure"]'),
    ).toBeNull();
  });

  it('regroups when a reader chooses another grouping', async () => {
    const user = userEvent.setup();
    renderScreen();
    await spendRows();
    await user.selectOptions(
      within(screen.getByTestId('ai-grouping')).getByRole('combobox'),
      'model',
    );
    expect(await screen.findByText('NovaCanvas')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Spend by model' })).toBeInTheDocument();
  });

  it('states the period, its measured total and the connected providers', async () => {
    renderScreen();
    const total = await screen.findByTestId('ai-spend-total');
    expect(total.textContent).toContain('September 2026');
    expect(within(total).getByTestId('figure')).toHaveAttribute('data-provenance', 'measured');
    expect(screen.getByTestId('ai-connected').textContent).toBe(
      'Connected: Fake OpenAI (OpenAI).',
    );
  });

  it('says no AI spend was seen rather than a total of nought', async () => {
    renderScreen('/analyze/ai', aiSpendNoneFixture());
    const none = await screen.findByTestId('ai-spend-none');
    expect(none).toBeInTheDocument();
    expect(within(screen.getByTestId('ai-spend')).queryAllByTestId('figure')).toEqual([]);
  });

  it('shows a failure as its typed cause and draws no figure', async () => {
    renderScreen('/analyze/ai', undefined, new Error('AccessDenied: the role was refused'));
    // All three panels, each its own read, once every one has settled rather than the first.
    await waitFor(() => {
      const states = screen
        .getAllByTestId('state')
        .map((one) => one.getAttribute('data-state'));
      expect(states).toEqual(['failed', 'failed', 'failed']);
    });
    expect(screen.queryAllByTestId('figure')).toEqual([]);
  });
});

describe('AiSpendScreen, callers', () => {
  it('prices every caller as modelled, and one the bill priced nothing for as not priced', async () => {
    renderScreen();
    const panel = await screen.findByTestId('ai-callers');
    const rows = await within(panel).findAllByTestId('ai-caller-row');
    expect(rows).toHaveLength(aiCallersFixture().data.callers.length);
    const costs = rows.map((row) => within(row).getByTestId('ai-caller-cost'));
    const priced = costs.filter(
      (cell) => cell.querySelector('[data-testid="figure"]') !== null,
    );
    for (const cell of priced) {
      expect(cell.querySelector('[data-provenance]')).toHaveAttribute(
        'data-provenance',
        'modelled',
      );
    }
    expect(costs.map((cell) => cell.textContent)).toContain('not priced');
  });
});

describe('AiSpendScreen, provider callers', () => {
  it('names a provider caller by its key where it names no one, beside its project', async () => {
    renderScreen();
    const panel = await screen.findByTestId('ai-callers');
    const rows = await within(panel).findAllByTestId('ai-caller-row');
    const keyed = present(
      rows.find((row) => row.textContent.includes('key key-fake-research')),
      'the provider row',
    );
    expect(within(keyed).getByTestId('ai-caller-workspace').textContent).toBe('proj-research');
    const logged = present(rows[0], 'the logs row');
    expect(within(logged).getByTestId('ai-caller-workspace').textContent).toBe('eu-west-1');
  });
});

describe('AiSpendScreen, GPU instances', () => {
  it('says not published for an agent that published nothing, never nought percent', async () => {
    renderScreen();
    const panel = await screen.findByTestId('ai-gpu');
    const rows = await within(panel).findAllByTestId('ai-gpu-row');
    const silent = present(
      rows.find((row) => row.getAttribute('data-utilization') === 'not published'),
      'the silent row',
    );
    expect(within(silent).getByTestId('ai-gpu-average').textContent).toBe('not published');
    expect(within(silent).queryByTestId('percent-figure')).toBeNull();
  });

  it('says how many of the billed days a partly published agent covered', async () => {
    renderScreen();
    const rows = await within(await screen.findByTestId('ai-gpu')).findAllByTestId(
      'ai-gpu-row',
    );
    const partly = present(
      rows.find((row) => row.getAttribute('data-utilization') === 'partly published'),
      'the partly row',
    );
    expect(within(partly).getByTestId('ai-gpu-published').textContent).toBe(
      '12 of 30 days, peak 71.00%',
    );
    expect(within(partly).getByTestId('percent-figure').textContent).toBe('18.5%');
  });
});

describe('accessibility', () => {
  it('has no violations', async () => {
    const { container } = renderScreen();
    await spendRows();
    await within(screen.getByTestId('ai-gpu')).findAllByTestId('ai-gpu-row');
    expect(await violationsIn(container)).toEqual([]);
  });
});
