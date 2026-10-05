import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import tokens from '../../tokens.css?raw';
import {
  BarChart,
  HEAT_FLOOR,
  Heatmap,
  KpiTile,
  StackedArea,
  StackedBar,
  Treemap,
} from '../charts';

/**
 * TASK-P8-005: Meter's chart set, hand built in SVG.
 *
 * Every chart carries a table a keyboard and a screen reader can use, and each test here
 * reads the numbers that table states and the marks the chart drew, and holds them equal.
 * A chart whose drawing and whose table disagree is two answers to one question.
 */

const money = (value: number): string => `$${value.toFixed(2)}`;

/** The numbers a chart's table states, in reading order. */
function stated(container: HTMLElement): number[] {
  return [...container.querySelectorAll('table td[data-value]')]
    .map((cell) => cell.getAttribute('data-value'))
    .filter((value): value is string => value !== null && value !== '')
    .map(Number);
}

function numberAttr(element: Element | null, name: string): number {
  return Number(element?.getAttribute(name));
}

/** The top edge of an area path: the first `count` points it draws. */
function topEdge(path: Element, count: number): number[] {
  const d = path.getAttribute('d') ?? '';
  return [...d.matchAll(/[ML](-?[\d.]+) (-?[\d.]+)/g)].slice(0, count).map((m) => Number(m[2]));
}

describe('StackedArea', () => {
  const series = [
    { key: 'ec2', label: 'EC2', provenance: 'measured' as const, values: [10, 20, 30] },
    { key: 's3', label: 'S3', provenance: 'measured' as const, values: [5, 5, 10] },
  ];

  it('draws each layer at the height its table states, stacked', () => {
    const { container } = render(
      <StackedArea
        periods={['Jan', 'Feb', 'Mar']}
        series={series}
        label="Spend"
        format={money}
      />,
    );
    const svg = container.querySelector('svg[role="img"]');
    const top = numberAttr(svg, 'data-top');
    const height = numberAttr(svg, 'data-height');
    const toValue = (y: number): number => ((height - y) / height) * top;
    const layers = [...container.querySelectorAll('[data-testid="area-layer"]')];
    expect(layers).toHaveLength(2);
    const [base, upper] = layers;
    expect(topEdge(base as Element, 3).map(toValue)).toEqual(
      [10, 20, 30].map((v) => expect.closeTo(v, 1) as unknown as number),
    );
    // The second layer sits on the first, so its top edge is the running total.
    expect(topEdge(upper as Element, 3).map(toValue)).toEqual(
      [15, 25, 40].map((v) => expect.closeTo(v, 1) as unknown as number),
    );
    expect(stated(container)).toEqual([10, 20, 30, 5, 5, 10]);
  });

  it('draws a forecast as a dashed band and the budget pace as its own line', () => {
    const { container } = render(
      <StackedArea
        periods={['Jan', 'Feb', 'Mar', 'Apr']}
        series={[
          { key: 'all', label: 'All', provenance: 'measured', values: [10, 20, 30, null] },
        ]}
        forecast={{ low: [null, null, 30, 35], high: [null, null, 30, 45] }}
        pace={[25, 50, 75, 100]}
        label="Spend against budget"
        format={money}
      />,
    );
    expect(container.querySelector('[data-testid="forecast-band"]')).toHaveClass(
      'meter-mark-forecast',
    );
    expect(container.querySelector('[data-testid="budget-pace"]')).toHaveClass('meter-pace');
    const rows = [...container.querySelectorAll('table tbody th')].map(
      (cell) => cell.textContent,
    );
    expect(rows).toEqual(['All', 'Forecast, low', 'Forecast, high', 'Budget pace']);
  });

  it('says nothing is collected rather than drawing an empty frame', () => {
    render(<StackedArea periods={['Jan']} series={[]} label="Spend" format={money} />);
    expect(screen.getByTestId('chart-absent')).toHaveAttribute('data-state', 'never-collected');
  });
});

describe('StackedBar', () => {
  it('draws each segment at the width its table states, modelled ones hatched', () => {
    const { container } = render(
      <StackedBar
        categories={['AmazonEC2', 'AmazonS3']}
        series={[
          { key: 'prod', label: 'Production', provenance: 'measured', values: [60, 20] },
          { key: 'dev', label: 'Development', provenance: 'modelled', values: [40, 10] },
        ]}
        label="Spend by service and environment"
        format={money}
      />,
    );
    const segments = [...container.querySelectorAll('[data-testid="bar-segment"]')];
    expect(segments).toHaveLength(4);
    // The widest row is the scale: 100 here, so a width is its value.
    for (const segment of segments) {
      expect(numberAttr(segment, 'width')).toBeCloseTo(numberAttr(segment, 'data-value'), 1);
    }
    expect(
      segments.filter((one) => one.classList.contains('meter-mark-modelled')),
    ).toHaveLength(2);
    expect(container.querySelectorAll('[data-testid="hatch-over"]')).toHaveLength(2);
    expect(stated(container)).toEqual([60, 40, 100, 20, 10, 30]);
  });
});

describe('Treemap', () => {
  it('gives each item an area in proportion to its value', () => {
    const items = [
      { label: 'EC2', value: 60 },
      { label: 'S3', value: 25 },
      { label: 'RDS', value: 15 },
    ];
    const { container } = render(
      <Treemap items={items} provenance="measured" label="Spend by service" format={money} />,
    );
    const cells = [...container.querySelectorAll('[data-testid="treemap-cell"]')];
    const area = (cell: Element): number =>
      numberAttr(cell, 'width') * numberAttr(cell, 'height');
    const total = cells.reduce((sum, cell) => sum + area(cell), 0);
    for (const cell of cells) {
      expect(area(cell) / total).toBeCloseTo(numberAttr(cell, 'data-value') / 100, 2);
    }
    expect(stated(container)).toEqual([60, 25, 15]);
  });
});

describe('Heatmap', () => {
  it('shades each cell by the value its table states', () => {
    const values = [
      [1, 2, 3, 4],
      [0, 4, 2, 1],
    ];
    const { container } = render(
      <Heatmap
        rows={['Mon', 'Tue']}
        columns={['00', '06', '12', '18']}
        values={values}
        provenance="measured"
        label="Spend by hour"
        format={money}
      />,
    );
    const cells = [...container.querySelectorAll('[data-testid="heat-cell"]')];
    const max = 4;
    for (const cell of cells) {
      const shade = numberAttr(cell, 'fill-opacity');
      expect(((shade - HEAT_FLOOR) / (1 - HEAT_FLOOR)) * max).toBeCloseTo(
        numberAttr(cell, 'data-value'),
        1,
      );
    }
    expect(stated(container)).toEqual(values.flat());
  });
});

describe('KpiTile', () => {
  it('states the change against the previous period and draws its trend', () => {
    const { container } = render(
      <KpiTile
        label="Effective Cost"
        value={1200}
        previous={1000}
        points={[900, 1000, 1100, 1200]}
        provenance="measured"
        format={money}
        period="last month"
      />,
    );
    expect(screen.getByTestId('kpi-value')).toHaveTextContent('$1200.00');
    expect(screen.getByTestId('kpi-delta')).toHaveTextContent('+20.0% against last month');
    expect(screen.getByTestId('sparkline')).toBeInTheDocument();
    expect(stated(container)).toEqual([1200, 1000, 200]);
  });

  it('says a figure is missing rather than drawing it as zero', () => {
    render(
      <KpiTile
        label="Effective Cost"
        value={null}
        previous={1000}
        points={[]}
        provenance="measured"
        format={money}
        period="last month"
      />,
    );
    expect(screen.getByTestId('kpi-value')).toHaveTextContent('Not yet collected');
    expect(screen.queryByTestId('kpi-delta')).toBeNull();
  });
});

describe('BarChart, wrapped into the set', () => {
  it('carries a table of the bars it draws', () => {
    const { container } = render(
      <BarChart
        points={[
          { label: '1 Oct', value: 4 },
          { label: '2 Oct', value: 8 },
        ]}
        provenance="measured"
        label="Daily spend"
        format={money}
      />,
    );
    expect(stated(container)).toEqual([4, 8]);
  });
});

describe('one set of marks', () => {
  it('draws measured solid, modelled hatched and forecast dashed', () => {
    expect(tokens).toMatch(/\.meter-mark-modelled\s*\{[^}]*fill-opacity/);
    expect(tokens).toMatch(/\.meter-mark-forecast\s*\{[^}]*stroke-dasharray/);
    expect(tokens).toMatch(/\.meter-pace\s*\{[^}]*stroke-dasharray/);
  });

  it('moves nothing, so reduced motion has nothing to stop', () => {
    const rules = tokens.match(/\.meter-(series|mark|pace|heat)[^{]*\{[^}]*\}/g) ?? [];
    expect(rules.length).toBeGreaterThan(0);
    for (const rule of rules) {
      expect(rule).not.toMatch(/transition|animation/);
    }
  });
});
