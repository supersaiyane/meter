import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { RankedBars } from '../RankedBars';
import { rankedRows } from '../rankedRows';
import { violationsIn } from './axe';

/**
 * The cases that carry this file are about the collapse and the share.
 *
 * A ranked chart fails quietly. A total computed after the remainder was collapsed rather than
 * before it makes every share too large and every bar too long, and the picture still looks
 * plausible: the rows are in the right order, the biggest is still biggest, and nothing about it
 * looks wrong. So the arithmetic is tested at its source rather than through the rendering.
 */

const FORMAT = (value: number) => `$${value.toFixed(0)}`;

describe('rankedRows', () => {
  it('takes the share against the whole, not against the part that fitted', () => {
    // The failure this guards. Four rows of 25 each, a limit of two: the two shown are 25
    // percent each and the collapsed pair is 50 percent. Summing after the collapse would
    // make them 50 and 50 and lose the remainder entirely.
    const rows = rankedRows(
      [
        { label: 'a', value: 25 },
        { label: 'b', value: 25 },
        { label: 'c', value: 25 },
        { label: 'd', value: 25 },
      ],
      2,
      'rest',
    );
    expect(rows).toHaveLength(3);
    expect(rows[0]?.share).toBeCloseTo(0.25);
    expect(rows[2]?.share).toBeCloseTo(0.5);
    // And the shares still add to one, which is the property the whole drawing rests on.
    expect(rows.reduce((sum, row) => sum + row.share, 0)).toBeCloseTo(1);
  });

  it('says how many rows the remainder stands for', () => {
    // A chart showing the top eight of forty without saying so lies by omission.
    const many = Array.from({ length: 12 }, (_, index) => ({
      label: `row-${String(index)}`,
      value: 10,
    }));
    const rows = rankedRows(many, 8, 'smaller owners');
    expect(rows).toHaveLength(9);
    expect(rows[8]?.label).toBe('smaller owners, 4 more');
    expect(rows[8]?.value).toBe(40);
  });

  it('collapses nothing when everything fits', () => {
    const rows = rankedRows([{ label: 'only', value: 5 }], 8, 'rest');
    expect(rows).toHaveLength(1);
    expect(rows[0]?.label).toBe('only');
  });

  it('ranks largest first whatever order it was given', () => {
    const rows = rankedRows(
      [
        { label: 'small', value: 1 },
        { label: 'large', value: 9 },
      ],
      8,
      'rest',
    );
    expect(rows.map((row) => row.label)).toEqual(['large', 'small']);
  });

  it('draws nothing rather than dividing by zero when every value is zero', () => {
    // A period whose every group is zero is a real state, and the shares are zero rather than
    // NaN, which would render as a bar of width NaN percent and silently disappear.
    const rows = rankedRows([{ label: 'a', value: 0 }], 8, 'rest');
    expect(rows[0]?.share).toBe(0);
  });
});

describe('RankedBars', () => {
  it('writes every value as text, so the bars are never the only carrier', () => {
    // The bars are aria-hidden decoration. That is only honest if the number is written down.
    render(
      <RankedBars
        points={[
          { label: 'AmazonEC2', value: 300 },
          { label: 'AmazonRDS', value: 100 },
        ]}
        format={FORMAT}
        provenance="measured"
      />,
    );
    const values = screen.getAllByTestId('ranked-value');
    expect(values[0]).toHaveTextContent('$300');
    expect(screen.getAllByTestId('ranked-share')[0]).toHaveTextContent('75.0%');
  });

  it('marks a gap row as a gap rather than as an owner', () => {
    render(
      <RankedBars
        points={[
          { label: 'platform', value: 60 },
          { label: 'nobody tagged this', value: 40, isGap: true },
        ]}
        format={FORMAT}
        provenance="measured"
      />,
    );
    const rows = screen.getAllByTestId('ranked-row');
    expect(rows[0]).toHaveAttribute('data-gap', 'false');
    expect(rows[1]).toHaveAttribute('data-gap', 'true');
  });

  it('renders nothing at all rather than an empty frame', () => {
    // An empty chart reads as broken. The screen around it says what an absence means.
    const { container } = render(
      <RankedBars points={[]} format={FORMAT} provenance="measured" />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('hatches a modelled breakdown, so a saving never reads as a measured cost', () => {
    // The reason provenance is required rather than defaulted. A modelled saving drawn with the
    // same solid fill as a measured cost is the one claim this product cannot get wrong, and the
    // hatch is the same mark a figure and a bar chart already use for it.
    render(
      <RankedBars
        points={[{ label: 'EBS_UNATTACHED', value: 64 }]}
        format={FORMAT}
        provenance="modelled"
      />,
    );
    expect(screen.getByTestId('ranked-bars')).toHaveAttribute('data-provenance', 'modelled');
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <RankedBars
        points={[{ label: 'one', value: 1 }]}
        format={FORMAT}
        provenance="measured"
      />,
    );
    expect(await violationsIn(container)).toEqual([]);
  });
});
