import { describe, expect, it } from 'vitest';

import type { ApiCitation } from '../../api/types';
import { amountOf, citeProse, decimalPlaces, figureUnit } from '../citations';

/**
 * P7 spec section 5.2, the rules under the citation component.
 *
 * The prose holds placeholders and the screen puts the values in, so the split is where a
 * value could be lost, duplicated or attached to the wrong citation, and the unit is where a
 * count could be drawn as dollars. Both are asserted without a renderer.
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
    provenance: 'measured',
    as_of: '2026-10-03T04:00:00Z',
    ...partial,
  };
}

describe('citeProse', () => {
  it('splits on the placeholders and numbers the citations by first use', () => {
    const total = citation({ placeholder: 'total' });
    const service = citation({ placeholder: 'service', kind: 'label', value: 'AmazonEC2' });
    const { parts, numbered } = citeProse('{{service}} cost {{total}}.', [total, service]);
    expect(parts).toEqual([
      { kind: 'cited', citation: service, number: 1 },
      { kind: 'text', text: ' cost ' },
      { kind: 'cited', citation: total, number: 2 },
      { kind: 'text', text: '.' },
    ]);
    expect(numbered).toEqual([
      { citation: service, number: 1 },
      { citation: total, number: 2 },
    ]);
  });

  it('keeps one number for a name the prose uses twice', () => {
    const total = citation({ placeholder: 'total' });
    const { parts, numbered } = citeProse('{{total}}, and again {{total}}', [total]);
    const numbers = parts.flatMap((part) => (part.kind === 'cited' ? [part.number] : []));
    expect(numbers).toEqual([1, 1]);
    expect(numbered).toHaveLength(1);
  });

  it('marks a placeholder no citation claims, rather than dropping it or showing the braces', () => {
    const { parts } = citeProse('spent {{total}}', []);
    expect(parts).toEqual([
      { kind: 'text', text: 'spent ' },
      { kind: 'uncited', name: 'total' },
    ]);
  });

  it('still lists a citation the prose never uses, after the ones it does', () => {
    const used = citation({ placeholder: 'used' });
    const unused = citation({ placeholder: 'unused' });
    const { numbered } = citeProse('{{used}}', [unused, used]);
    expect(numbered.map((one) => [one.citation.placeholder, one.number])).toEqual([
      ['used', 1],
      ['unused', 2],
    ]);
  });

  it('leaves braces that are not a placeholder as text, and parses nothing as markup', () => {
    const { parts } = citeProse('<b>{{Total}}</b>', []);
    expect(parts).toEqual([{ kind: 'text', text: '<b>{{Total}}</b>' }]);
  });
});

describe('figureUnit', () => {
  it('reads money from the field name, through a row selector', () => {
    for (const field of [
      'data.current.effective_cost',
      'data[name=AmazonEC2].effective_cost',
      'data[finding_id=abc].monthly_cost',
      'data.change',
      'data.clusters[cluster_name=prod.eks].total',
      'effective_cost summed over the week',
    ]) {
      expect(figureUnit(citation({ placeholder: 'x', field }))).toBe('usd');
    }
  });

  it('reads everything else as a count, including the envelope coverage', () => {
    for (const field of [
      'data.current.line_items',
      'data.accounts_in_scope',
      'meta.scope_coverage.total',
      'data[instance=m5.cost].runs_per_day',
    ]) {
      expect(figureUnit(citation({ placeholder: 'x', field }))).toBe('count');
    }
  });
});

describe('amountOf', () => {
  it('reads the decimals the API writes, including a scaled zero', () => {
    expect(amountOf('3781.9335')).toBe(3781.9335);
    expect(amountOf('-12.5')).toBe(-12.5);
    expect(amountOf('0E-10')).toBe(0);
  });

  it('returns nothing for a value that is not a number, never a zero', () => {
    for (const value of ['', ' ', 'NaN', 'Infinity', 'twelve', '1e999']) {
      expect(amountOf(value)).toBeNull();
    }
  });
});

describe('decimalPlaces', () => {
  it('counts the places a decimal arrived with, so a fraction is drawn as one', () => {
    expect(decimalPlaces('0.4000')).toBe(4);
    expect(decimalPlaces('2.5')).toBe(1);
    expect(decimalPlaces('455')).toBe(0);
    expect(decimalPlaces('0E-10')).toBe(10);
    expect(decimalPlaces('1.5E+2')).toBe(0);
  });

  it('claims no places for text that is not a decimal', () => {
    expect(decimalPlaces('twelve')).toBe(0);
  });
});
