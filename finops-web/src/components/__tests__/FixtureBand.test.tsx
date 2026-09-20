import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { FixtureBand } from '../FixtureBand';
import { violationsIn } from './axe';

describe('FixtureBand', () => {
  it('says nothing when the data came from a route', () => {
    render(<FixtureBand source="route" />);
    expect(screen.queryByTestId('fixture-band')).toBeNull();
  });

  it('says so, visibly, when the data is invented', () => {
    render(<FixtureBand source="fixture" />);
    expect(screen.getByTestId('fixture-band')).toHaveTextContent(/FIXTURE DATA/);
  });

  it('announces itself to assistive technology', () => {
    // A reader who cannot see the band is the reader most at risk of trusting
    // the numbers underneath it.
    render(<FixtureBand source="fixture" />);
    expect(screen.getByTestId('fixture-band')).toHaveAttribute('role', 'status');
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<FixtureBand source="fixture" />);
    expect(await violationsIn(container)).toEqual([]);
  });
});
