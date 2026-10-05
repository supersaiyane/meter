import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { ApiCitation } from '../../api/types';
import { CitedProse } from '../CitedProse';

/**
 * The citation component's safety branches, P7 spec section 5.2.
 *
 * Prose and cited values come from a model and from tool results, so each case is a value that
 * would mislead or do harm if drawn the obvious way: a figure that is not a number drawn as
 * zero, markup in the prose parsed as markup, a placeholder with no citation drawn as braces, a
 * provenance that is neither of the two drawn as measured, a fraction drawn as a whole number,
 * a figure with no unit drawn in one the screen chose.
 */

function citation(
  partial: Partial<ApiCitation> & Pick<ApiCitation, 'placeholder'>,
): ApiCitation {
  return {
    tool: 'get_cost_summary',
    call_id: 'toolu_one',
    field: 'data.current.effective_cost',
    value: '10.00',
    kind: 'figure',
    unit: 'usd',
    provenance: 'measured',
    as_of: '2026-10-03T04:00:00Z',
    ...partial,
  };
}

function renderProse(prose: string, citations: readonly ApiCitation[]) {
  return render(
    <CitedProse scope="s1" prose={prose} citations={citations} readAt="2026-10-04T08:12:09Z" />,
  );
}

/** The cited value in the sentence for one placeholder. */
function valueFor(placeholder: string): HTMLElement {
  const found = screen
    .getAllByTestId('cited-value')
    .find((one) => one.dataset['placeholder'] === placeholder);
  if (found === undefined) {
    throw new Error(`${placeholder} is not in the sentence`);
  }
  return found;
}

/** The numeral a Figure drew in the sentence for one placeholder. */
function numeralOf(placeholder: string): string | null | undefined {
  return valueFor(placeholder).querySelector('.meter-numeral')?.textContent;
}

describe('a figure that is not a number', () => {
  it('is drawn as unrecognised in the sentence and in its entry, never as zero', () => {
    renderProse('spent {{total}}.', [citation({ placeholder: 'total', value: 'twelve' })]);
    expect(screen.queryAllByTestId('figure')).toEqual([]);
    for (const drawn of [valueFor('total'), screen.getByTestId('citation-value')]) {
      expect(drawn).toHaveTextContent('UNRECOGNISED');
      expect(drawn.textContent).not.toContain('$');
      expect(drawn.textContent).not.toMatch(/0/);
    }
  });
});

describe('markup in what the model or a tool wrote', () => {
  it('is drawn as text, in the prose and in a label, and never becomes an element', () => {
    const markup = '<img src=x onerror=alert(1)>';
    const { container } = renderProse(`${markup} cost {{service}}`, [
      citation({ placeholder: 'service', kind: 'label', value: markup, unit: null }),
    ]);
    expect(container.querySelector('img')).toBeNull();
    expect(screen.getByTestId('cited-prose').textContent).toContain(markup);
    expect(within(valueFor('service')).getByTestId('cited-label').textContent).toBe(markup);
  });
});

describe('a placeholder no citation claims', () => {
  it('is drawn as unrecognised, naming it, rather than as braces or as nothing', () => {
    const { container } = renderProse('spent {{total}}', []);
    const drift = container.querySelector('[data-cause="SchemaDrift"]');
    expect(drift).toHaveTextContent('UNRECOGNISED');
    expect(drift).toHaveTextContent('total');
    expect(screen.getByTestId('cited-prose').textContent).not.toContain('{{');
  });
});

describe('a provenance that is neither measured nor modelled', () => {
  it('is drawn as unrecognised, never as a measurement', () => {
    const provenance = 'forecast' as unknown as ApiCitation['provenance'];
    renderProse('spent {{total}}', [citation({ placeholder: 'total', provenance })]);
    expect(screen.queryAllByTestId('figure')).toEqual([]);
    expect(valueFor('total')).toHaveTextContent('UNRECOGNISED');
  });
});

describe('a count that is not whole', () => {
  it('is drawn to its own precision, never rounded to a whole number or to zero', () => {
    const runs = 'data[finding_id=abc].runs_per_day';
    renderProse('runs {{slow}} and {{fast}} a day over {{items}} line items', [
      citation({ placeholder: 'slow', field: runs, value: '0.4000', unit: 'count' }),
      citation({ placeholder: 'fast', field: runs, value: '2.5', unit: 'count' }),
      citation({
        placeholder: 'items',
        field: 'data.current.line_items',
        value: '455',
        unit: 'count',
      }),
    ]);
    expect(numeralOf('slow')).toBe('0.4');
    expect(numeralOf('fast')).toBe('2.5');
    expect(numeralOf('items')).toBe('455');
  });
});

describe('a figure in dollars under a field name with no money word in it', () => {
  it('is drawn as dollars, because its unit is what the tool declared and not its name', () => {
    renderProse('owed {{owed}}', [
      citation({ placeholder: 'owed', field: 'data[name=a].overage', value: '1234.5' }),
    ]);
    expect(numeralOf('owed')).toBe('$1,234.50');
  });
});

describe('a figure with no unit', () => {
  it('is drawn as unrecognised in the sentence and in its entry, never in a unit guessed', () => {
    // A field whose name says money, which the screen once read as dollars on that alone.
    renderProse('spent {{total}}.', [
      citation({ placeholder: 'total', field: 'data.current.effective_cost', unit: null }),
    ]);
    expect(screen.queryAllByTestId('figure')).toEqual([]);
    for (const drawn of [valueFor('total'), screen.getByTestId('citation-value')]) {
      expect(drawn).toHaveTextContent('UNRECOGNISED');
      expect(drawn).toHaveTextContent('carries no unit');
      expect(drawn.textContent).not.toContain('$');
      expect(drawn.textContent).not.toContain('10');
    }
  });
});
