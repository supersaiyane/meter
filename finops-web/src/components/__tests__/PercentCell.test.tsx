import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { PercentCell } from '../PercentCell';
import { violationsIn } from './axe';

/**
 * The case that carries this file is the absence, which is constraint 5 in one component.
 *
 * A commitment that has not started and a service with nothing eligible both have no percentage.
 * Drawing either as an empty track says the measurement came back zero, which for a commitment
 * means the money was wasted. The words and no bar is the only honest rendering, and it is the
 * thing a future edit is most likely to undo while every rendering assertion still passes.
 */

describe('PercentCell', () => {
  it('says there is no figure rather than drawing an empty track', () => {
    render(<PercentCell fraction={null} absent="not started" provenance="measured" />);
    expect(screen.getByTestId('percent-absent')).toHaveTextContent('not started');
    expect(screen.queryByTestId('percent-track')).toBeNull();
    // And no figure either, because a percentage that does not exist must not be printed.
    expect(screen.queryByTestId('percent-figure')).toBeNull();
  });

  it('draws a real zero as a real zero', () => {
    // Distinct from the case above and the reason they must not share a rendering. Nought
    // percent coverage on an eligible service is a finding somebody acts on.
    render(<PercentCell fraction={0} absent="nothing eligible" provenance="measured" />);
    expect(screen.getByTestId('percent-figure')).toHaveTextContent('0.0%');
    expect(screen.getByTestId('percent-track')).toBeInTheDocument();
  });

  it('clamps the bar without rounding the figure', () => {
    // A utilization over one is possible where a plan covered more than it committed. The bar
    // cannot run past its track, and the number must still say what it was, because the figure
    // is the evidence and the bar is only a way of comparing it.
    render(<PercentCell fraction={1.07} absent="none" provenance="measured" />);
    expect(screen.getByTestId('percent-figure')).toHaveTextContent('107.0%');
    expect(screen.getByTestId('percent-track').querySelector('i')).toHaveStyle({
      width: '100%',
    });
  });

  it('carries provenance, so a modelled percentage is never drawn as a measured one', () => {
    render(<PercentCell fraction={0.5} absent="none" provenance="modelled" />);
    expect(screen.getByTestId('percent-cell')).toHaveAttribute('data-provenance', 'modelled');
  });

  it('hides the bar from the accessibility tree, because the figure is already read', async () => {
    const { container } = render(
      <PercentCell fraction={0.4} absent="none" provenance="measured" />,
    );
    expect(screen.getByTestId('percent-track')).toHaveAttribute('aria-hidden', 'true');
    expect(await violationsIn(container)).toEqual([]);
  });
});
