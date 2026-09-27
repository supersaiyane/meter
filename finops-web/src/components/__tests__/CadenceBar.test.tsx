import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { CadenceBar } from '../CadenceBar';
import { latenessOf } from '../lateness';
import { violationsIn } from './axe';

/**
 * The cases that carry this file are the two absences and the clamp.
 *
 * A collector with no age and a collector with no cadence both have undefined lateness, and they
 * are not the same fact: one has never worked and the other is not scheduled. Rendering either as
 * an empty track says the measurement came back zero, and for freshness zero means collected this
 * instant, which is the exact opposite of what is true.
 *
 * The clamp is the other one. A collector at nine times its cadence and one at two and a half
 * draw identically once the bar stops, so the number beside it has to keep telling the truth and
 * the end of the track has to say it ran off the scale.
 */

function fillOf(): number {
  const style = screen.getByTestId('cadence-track').querySelector('i')?.getAttribute('style');
  return Number(/width:\s*([\d.]+)%/.exec(style ?? '')?.[1]);
}

describe('latenessOf', () => {
  it('divides the age by the collector its own cadence', () => {
    // The whole design. A daily collector six hours old is at a quarter and an hourly one six
    // hours old is at six, and a single threshold would call one of them wrong every time.
    expect(latenessOf(21600, 86400)).toBeCloseTo(0.25);
    expect(latenessOf(21600, 3600)).toBeCloseTo(6);
  });

  it('is undefined with no age and undefined with no cadence', () => {
    expect(latenessOf(null, 3600)).toBeNull();
    expect(latenessOf(300, null)).toBeNull();
  });

  it('refuses a cadence of zero rather than returning infinity', () => {
    // A zero cadence would divide to Infinity, which renders as a bar of width Infinity percent
    // and silently disappears, so a collector scheduled at nought would vanish from the screen.
    expect(latenessOf(300, 0)).toBeNull();
  });
});

describe('CadenceBar', () => {
  it('says a collector has never run rather than drawing it at nothing', () => {
    render(<CadenceBar ageSeconds={null} cadenceSeconds={3600} />);
    expect(screen.getByTestId('cadence-absent')).toHaveTextContent('never collected');
    expect(screen.queryByTestId('cadence-track')).toBeNull();
  });

  it('gives an unscheduled collector a different sentence from one that never ran', () => {
    // Two absences that need different actions. One is fixed by making the collection work, the
    // other by scheduling it, and a shared sentence would send somebody to the wrong place.
    render(<CadenceBar ageSeconds={300} cadenceSeconds={null} />);
    expect(screen.getByTestId('cadence-absent')).toHaveTextContent('nothing schedules this');
    expect(screen.getByTestId('cadence-absent')).not.toHaveTextContent('never collected');
  });

  it('puts the due point in the middle and a fresh collector short of it', () => {
    // Half a cadence old, so the fill reaches a quarter of a track that runs to twice the
    // cadence. The reading is which side of the tick the fill ends on, and nothing else.
    render(<CadenceBar ageSeconds={1800} cadenceSeconds={3600} />);
    expect(fillOf()).toBeCloseTo(25);
    expect(screen.getByTestId('cadence')).toHaveAttribute('data-state', 'due');
    const tick = screen.getByTestId('cadence-track').querySelector('b');
    expect(tick).toHaveStyle({ left: '50%' });
  });

  it('marks a collector past its cadence as over, on the tick itself', () => {
    // Exactly due is not late. The boundary matters because a collector sitting on its cadence
    // is the normal state of a healthy one, and flagging it would make the count useless.
    render(<CadenceBar ageSeconds={3600} cadenceSeconds={3600} />);
    expect(screen.getByTestId('cadence')).toHaveAttribute('data-state', 'due');
    expect(fillOf()).toBeCloseTo(50);
  });

  it('stops the bar past twice the cadence and keeps the number honest', () => {
    // Nine times its cadence. The bar cannot say nine, so it says it ran off the scale and the
    // multiple says nine, which is the half a reader acts on.
    render(<CadenceBar ageSeconds={32400} cadenceSeconds={3600} />);
    expect(fillOf()).toBeCloseTo(100);
    expect(screen.getByTestId('cadence')).toHaveAttribute('data-clamped', 'true');
    expect(screen.getByTestId('cadence-multiple')).toHaveTextContent('9.0x');
  });

  it('does not mark a bar that fits as running off the scale', () => {
    render(<CadenceBar ageSeconds={5400} cadenceSeconds={3600} />);
    expect(screen.getByTestId('cadence')).toHaveAttribute('data-clamped', 'false');
    expect(screen.getByTestId('cadence')).toHaveAttribute('data-state', 'over');
  });

  it('keeps two places under one cadence, where one place would read as zero', () => {
    // Five minutes into an hour. At one decimal place this is 0.1x, and a collector at 0.05 and
    // one at 0.4 would both render as nearly just collected.
    render(<CadenceBar ageSeconds={300} cadenceSeconds={3600} />);
    expect(screen.getByTestId('cadence-multiple')).toHaveTextContent('0.08x');
  });

  it('hides the bar from the accessibility tree and writes the number out', async () => {
    const { container } = render(<CadenceBar ageSeconds={1800} cadenceSeconds={3600} />);
    expect(screen.getByTestId('cadence-track')).toHaveAttribute('aria-hidden', 'true');
    expect(screen.getByTestId('cadence-multiple')).toBeInTheDocument();
    expect(await violationsIn(container)).toEqual([]);
  });
});
