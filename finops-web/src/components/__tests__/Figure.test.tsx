import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Figure } from '../Figure';
import type { Freshness } from '../provenance';
import { violationsIn } from './axe';

const NOW = new Date('2026-08-27T10:00:00Z');

const FRESH: Freshness = {
  asOf: new Date('2026-08-27T09:00:00Z'),
  collectedAt: new Date('2026-08-27T09:55:00Z'),
  cadenceSeconds: 3600,
};

describe('Figure', () => {
  it('renders_no_numeral_for_a_failure', async () => {
    // The rule the whole design exists to protect. Not zero, not a dash, not
    // blank. The cause and a way to act, and no numeral at all.
    const { container } = render(
      <Figure
        value={{
          kind: 'failed',
          cause: 'AccessDenied',
          remediation: 'The collector role is not assumable.',
        }}
        freshness={FRESH}
        now={NOW}
      />,
    );

    expect(container.querySelector('.meter-numeral')).toBeNull();
    expect(screen.getByText('ACCESS DENIED')).toBeInTheDocument();
    expect(screen.getByText('The collector role is not assumable.')).toBeInTheDocument();
    expect(await violationsIn(container)).toEqual([]);
  });

  it.each([
    ['Throttled', 'THROTTLED'],
    ['NotOptedIn', 'NOT ENABLED'],
    ['Unreachable', 'UNREACHABLE'],
    ['SchemaDrift', 'UNRECOGNISED'],
  ] as const)('renders %s as its label and never as a number', (cause, label) => {
    const { container } = render(
      <Figure
        value={{ kind: 'failed', cause, remediation: 'Do the thing.' }}
        freshness={FRESH}
        now={NOW}
      />,
    );
    expect(container.querySelector('.meter-numeral')).toBeNull();
    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it('nodata_renders_zero', () => {
    // And the one legitimate zero still works. A genuine zero and a refusal must
    // not compete, which is the distinction the product is built on.
    const { container } = render(
      <Figure
        value={{ kind: 'failed', cause: 'NoData', remediation: 'Nothing to read.' }}
        freshness={FRESH}
        now={NOW}
      />,
    );
    const numeral = container.querySelector('.meter-numeral');
    expect(numeral).not.toBeNull();
    expect(numeral?.textContent).toBe('$0.00');
    expect(screen.queryByText('ACCESS DENIED')).toBeNull();
  });

  it('provenance_survives_without_colour', () => {
    // Fill and label carry it independently. Colour fails for roughly eight
    // percent of men, and fails entirely in a photocopied board pack.
    const { container } = render(
      <Figure value={{ kind: 'modelled', amount: 312.1 }} freshness={FRESH} now={NOW} />,
    );
    const numeral = container.querySelector('.meter-numeral');
    expect(numeral?.textContent).toMatch(/^~/);
    expect(numeral?.className).toContain('meter-fill-modelled');
    expect(container.textContent).toContain('modelled');
  });

  it('says so when a modelled figure has no published accuracy', () => {
    // Worse looking and more honest.
    render(<Figure value={{ kind: 'modelled', amount: 10 }} freshness={FRESH} now={NOW} />);
    expect(screen.getByText(/accuracy not yet published/)).toBeInTheDocument();
  });

  it('never lets a wrapped line begin with the accuracy comma', () => {
    // In a narrow surface the accuracy clause wraps. With the comma leading
    // that clause it became the first character of the new line, which reads
    // as a typo. It belongs to the word before it, so the break falls after
    // "modelled," and not before the comma.
    const { container } = render(
      <Figure value={{ kind: 'modelled', amount: 200 }} freshness={FRESH} now={NOW} />,
    );
    const spans = [...container.querySelectorAll('span')];
    expect(spans.some((s) => s.textContent.trim().endsWith('modelled,'))).toBe(true);
    expect(spans.some((s) => s.textContent.trimStart().startsWith(','))).toBe(false);
  });

  it('carries a published accuracy when there is one', () => {
    render(
      <Figure
        value={{ kind: 'modelled', amount: 12400, accuracy: '+/- 9%' }}
        freshness={FRESH}
        now={NOW}
      />,
    );
    expect(screen.getByText(/\+\/- 9%/)).toBeInTheDocument();
  });

  it('forecast_renders_an_interval', () => {
    // ADR-0015 condition 2 as a rendering rule. Six to nine, never seven.
    const { container } = render(
      <Figure
        value={{ kind: 'forecast', low: 6, high: 9 }}
        freshness={FRESH}
        unit="count"
        now={NOW}
      />,
    );
    const numeral = container.querySelector('.meter-numeral');
    expect(numeral?.textContent).toBe('~ 6 to 9');
    expect(container.textContent).toContain('forecast');
  });

  it('all_three_provenances_are_distinguishable', () => {
    // TASK-P6-012. Each encoding that can carry provenance has to tell all three apart: the
    // attribute tests and styles key off, the fill class, the word, and the numeral. A pair
    // that agreed on every one would be a pair a reader could not tell apart either.
    const rendered = (
      [
        { kind: 'measured', amount: 7 },
        { kind: 'modelled', amount: 7 },
        { kind: 'forecast', low: 6, high: 9 },
      ] as const
    ).map((value) => {
      const { container, unmount } = render(
        <Figure value={value} freshness={FRESH} unit="count" now={NOW} />,
      );
      const wrapper = container.querySelector('[data-provenance]');
      const numeral = container.querySelector('.meter-numeral');
      const out = {
        attribute: wrapper?.getAttribute('data-provenance') ?? '',
        fill:
          Array.from(numeral?.classList ?? []).find((c) => c.startsWith('meter-fill-')) ?? '',
        text: container.textContent,
        numeral: numeral?.textContent ?? '',
      };
      unmount();
      return out;
    });
    expect(new Set(rendered.map((r) => r.attribute)).size).toBe(3);
    expect(new Set(rendered.map((r) => r.fill)).size).toBe(3);
    expect(new Set(rendered.map((r) => r.numeral)).size).toBe(3);
    for (const [index, word] of ['measured', 'modelled', 'forecast'].entries()) {
      expect(rendered[index]?.text).toContain(word);
    }
  });

  it('renders a measured figure solid and with no tilde', () => {
    const { container } = render(
      <Figure value={{ kind: 'measured', amount: 4201.55 }} freshness={FRESH} now={NOW} />,
    );
    const numeral = container.querySelector('.meter-numeral');
    expect(numeral?.textContent).toBe('$4,201.55');
    expect(numeral?.className).toContain('meter-fill-measured');
    expect(container.textContent).toContain('measured');
  });

  it('keeps trailing zeros so a column aligns', () => {
    const { container } = render(
      <Figure value={{ kind: 'measured', amount: 312 }} freshness={FRESH} now={NOW} />,
    );
    expect(container.querySelector('.meter-numeral')?.textContent).toBe('$312.00');
  });

  it('marks a stale figure against the collector cadence rather than a fixed age', () => {
    // A daily collector six hours old is fine. An hourly one is not.
    const hourly = render(
      <Figure
        value={{ kind: 'measured', amount: 1 }}
        freshness={{ ...FRESH, asOf: new Date('2026-08-27T03:00:00Z') }}
        now={NOW}
      />,
    );
    expect(hourly.getByTestId('freshness').dataset['stale']).toBe('true');

    const daily = render(
      <Figure
        value={{ kind: 'measured', amount: 1 }}
        freshness={{ ...FRESH, asOf: new Date('2026-08-27T03:00:00Z'), cadenceSeconds: 86400 }}
        now={NOW}
      />,
    );
    expect(daily.getAllByTestId('freshness')[1]?.dataset['stale']).toBe('false');
  });

  it('never says live or just now', () => {
    const { container } = render(
      <Figure value={{ kind: 'measured', amount: 1 }} freshness={FRESH} now={NOW} />,
    );
    expect(container.textContent).not.toContain('live');
    expect(container.textContent).not.toContain('just now');
  });

  it('reports no accessibility violations for any provenance', async () => {
    const { container } = render(
      <div>
        <Figure value={{ kind: 'measured', amount: 1 }} freshness={FRESH} now={NOW} />
        <Figure value={{ kind: 'modelled', amount: 2 }} freshness={FRESH} now={NOW} />
        <Figure value={{ kind: 'forecast', low: 3, high: 4 }} freshness={FRESH} now={NOW} />
      </div>,
    );
    expect(await violationsIn(container)).toEqual([]);
  });
});
