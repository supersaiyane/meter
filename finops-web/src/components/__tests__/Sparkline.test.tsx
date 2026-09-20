import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Sparkline } from '../Sparkline';

function pathOf(): string {
  const path = screen.getByTestId('sparkline').querySelector('path');
  return path?.getAttribute('d') ?? '';
}

function yValues(d: string): number[] {
  return [...d.matchAll(/[ML][\d.]+ ([\d.]+)/g)].map((match) => Number(match[1]));
}

describe('Sparkline', () => {
  it('draws a series that never changes down the middle', () => {
    // It drew it along the floor, because normalising a series with no range
    // put every point at zero. A module costing the same every day for thirty
    // days then drew the same line as one costing nothing at all. ISS-160.
    render(<Sparkline points={[4, 4, 4, 4]} provenance="measured" label="flat" />);
    expect(new Set(yValues(pathOf()))).toEqual(new Set([12]));
  });

  it('still puts the lowest point on the floor when there is a range', () => {
    // The pair. Without it the fix above would also pass if every series were
    // drawn down the middle.
    render(<Sparkline points={[0, 10]} provenance="measured" label="rising" />);
    expect(yValues(pathOf())).toEqual([24, 0]);
  });

  it('draws one point as nothing rather than as a flat line', () => {
    // One point is not a trend, and a flat line implies a stability nobody has
    // observed.
    render(<Sparkline points={[7]} provenance="measured" label="single" />);
    expect(screen.getByTestId('sparkline').dataset['empty']).toBe('true');
  });

  it('draws a modelled series dashed', () => {
    render(<Sparkline points={[1, 2, 3]} provenance="modelled" label="guess" />);
    expect(
      screen.getByTestId('sparkline').querySelector('path')?.getAttribute('stroke-dasharray'),
    ).toBe('3 2');
  });
});
