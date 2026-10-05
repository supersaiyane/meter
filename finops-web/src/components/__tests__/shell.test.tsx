import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { CoverageBanner } from '../CoverageBanner';
import { FreshnessIndicator } from '../FreshnessIndicator';
import { SeverityBadge } from '../SeverityBadge';
import { Sparkline } from '../Sparkline';
import { TypedError } from '../TypedError';
import { violationsIn } from './axe';

const NOW = new Date('2026-08-27T10:00:00Z');

describe('CoverageBanner', () => {
  it('says how much of the organization is visible', () => {
    render(<CoverageBanner coverage={[{ unit: 'accounts', visible: 42, total: 310 }]} />);
    expect(screen.getByText('Showing 42 of 310 accounts')).toBeInTheDocument();
    expect(screen.getByTestId('coverage').dataset['partial']).toBe('true');
  });

  it('confirms complete coverage rather than staying silent', () => {
    // The absence of a warning is not confirmation, and a reader needs
    // confirmation before treating a total as a total.
    render(<CoverageBanner coverage={[{ unit: 'accounts', visible: 310, total: 310 }]} />);
    expect(screen.getByText('Showing all 310 accounts')).toBeInTheDocument();
  });

  it('states each thing it counted rather than one ratio over both', () => {
    // Home holds a panel counted in accounts beside one counted in workspaces.
    // A single ratio across the two was true of neither: it read `0 of 3`.
    render(
      <CoverageBanner
        coverage={[
          { unit: 'workspaces', visible: 2, total: 3 },
          { unit: 'accounts', visible: 4, total: 4 },
        ]}
      />,
    );
    expect(screen.getByText('Showing 2 of 3 workspaces, all 4 accounts')).toBeInTheDocument();
  });

  it('says nothing has reported rather than implying full coverage', () => {
    render(<CoverageBanner coverage={[]} />);
    expect(screen.getByText('Coverage not yet reported')).toBeInTheDocument();
  });

  it('offers no way to dismiss it', () => {
    // A banner gets dismissed. The condition does not go away with it.
    const { container } = render(
      <CoverageBanner coverage={[{ unit: 'accounts', visible: 1, total: 2 }]} />,
    );
    expect(container.querySelector('button')).toBeNull();
  });
});

describe('FreshnessIndicator', () => {
  it('gives an absolute as_of and a relative collected age', () => {
    render(
      <FreshnessIndicator
        freshness={{
          asOf: new Date('2026-08-27T04:00:00Z'),
          collectedAt: new Date('2026-08-27T09:54:00Z'),
          cadenceSeconds: 86400,
        }}
        now={NOW}
      />,
    );
    // Absolute for as_of, because it is a claim about the world. An age for
    // collected_at, because a timestamp makes the reader do arithmetic.
    expect(screen.getByTestId('freshness').textContent).toContain('as of 2026-08-27 04:00');
    expect(screen.getByTestId('freshness').textContent).toContain('6 min ago');
  });

  it('treats an unknown cadence as stale rather than fine', () => {
    render(<FreshnessIndicator freshness={{ asOf: NOW, collectedAt: NOW }} now={NOW} />);
    expect(screen.getByTestId('freshness').dataset['stale']).toBe('true');
  });
});

describe('SeverityBadge', () => {
  it('carries rank as a shape count and a label, not only a colour', () => {
    render(<SeverityBadge level={4} />);
    expect(screen.getByText('high')).toBeInTheDocument();
    expect(screen.getByTestId('severity').textContent).toContain('■■■■');
  });
});

describe('Sparkline', () => {
  it('draws a modelled series dashed so it is not read as measured', () => {
    const { container } = render(
      <Sparkline points={[1, 2, 3]} provenance="modelled" label="Daily cost" />,
    );
    expect(container.querySelector('path')?.getAttribute('stroke-dasharray')).toBe('3 2');
  });

  it('draws nothing for a single point, because one point is not a trend', () => {
    render(<Sparkline points={[1]} provenance="measured" label="Daily cost" />);
    expect(screen.getByTestId('sparkline').dataset['empty']).toBe('true');
  });

  it('has a text alternative', async () => {
    const { container } = render(
      <Sparkline points={[1, 2]} provenance="measured" label="Daily cost" />,
    );
    expect(screen.getByRole('img', { name: /Daily cost, measured/ })).toBeInTheDocument();
    expect(await violationsIn(container)).toEqual([]);
  });
});

describe('TypedError', () => {
  it('announces the cause to assistive technology', () => {
    render(<TypedError cause="Throttled" remediation="Retrying shortly." />);
    expect(screen.getByRole('status')).toHaveTextContent('THROTTLED');
  });

  it('offers an action only when there is one to offer', () => {
    const { container } = render(
      <TypedError cause="AccessDenied" remediation="Check the role." />,
    );
    expect(container.querySelector('button')).toBeNull();
  });

  it('reports no accessibility violations', async () => {
    const { container } = render(
      <TypedError
        cause="AccessDenied"
        remediation="Check the role."
        actionLabel="Recheck"
        onAction={() => undefined}
      />,
    );
    expect(await violationsIn(container)).toEqual([]);
  });
});
