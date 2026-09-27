import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { CostScreen } from '../CostScreen';
import { Harness } from './Harness';
import { clientReturning } from './fixtures';
import {
  costByServiceFixture,
  costSummaryFixture,
  costTrendFixture,
} from '../../api/fixtures/cost';
import { violationsIn } from '../../components/__tests__/axe';

function renderCost(summary = costSummaryFixture()) {
  return render(
    <Harness
      client={clientReturning({
        '/api/v1/cost/summary': summary,
        '/api/v1/cost/by-service': costByServiceFixture(),
        '/api/v1/cost/trend': costTrendFixture(),
      })}
    >
      <CostScreen />
    </Harness>,
  );
}

describe('CostScreen', () => {
  it('says when the period is still open', async () => {
    // The most important thing on the page. A part month set beside a whole
    // one, unwarned, reads as spending having collapsed.
    renderCost();
    expect(await screen.findByTestId('cost-open')).toBeInTheDocument();
  });

  it('does not say it about a finished period', async () => {
    const finished = costSummaryFixture();
    const closed = {
      ...finished,
      data: { ...finished.data, current: { ...finished.data.current, is_open: false } },
    };
    renderCost(closed);
    await screen.findByTestId('cost-total');
    expect(screen.queryByTestId('cost-open')).not.toBeInTheDocument();
  });

  it('renders no comparison rather than a zero when there is no earlier period', async () => {
    // A change of nought would claim the estate spent the same as a month
    // nobody ever collected. Constraint 5 is about exactly that difference.
    const alone = costSummaryFixture();
    const first = { ...alone, data: { ...alone.data, previous: null, change: null } };
    renderCost(first);
    expect(await screen.findByTestId('cost-no-comparison')).toBeInTheDocument();
  });

  it('shows every service as measured and never as modelled', async () => {
    // A charge is what the provider billed. There is no model here for it to
    // be a projection of, so a modelled badge would be an invention.
    renderCost();
    await screen.findByTestId('ranked-bars');
    const figures = document.querySelectorAll('[data-testid="figure"]');
    expect(figures.length).toBeGreaterThan(0);
    for (const figure of figures) {
      expect(figure.getAttribute('data-provenance')).toBe('measured');
    }
  });

  it('puts the most expensive service first', async () => {
    renderCost();
    await screen.findByTestId('ranked-bars');
    const rows = [...document.querySelectorAll('tbody tr')];
    expect(rows[0]?.textContent).toContain('AmazonEC2');
    expect(rows[rows.length - 1]?.textContent).toContain('AWSLambda');
  });

  it('draws the period as a shape rather than a list of days', async () => {
    // Eighteen rows repeating one freshness label is not a trend, it is the
    // same sentence eighteen times around numbers nobody can compare.
    renderCost();
    await screen.findByTestId('ranked-bars');
    expect(screen.getByTestId('bar-chart')).toBeInTheDocument();
    // And it can be read off, which a sparkline by its own definition cannot. The peak is
    // labelled, so a reader asking why a week was expensive has a number to point at.
    expect(screen.getByTestId('bar-chart-peak')).toBeInTheDocument();
    expect(screen.getAllByTestId('cost-trend-day')).toHaveLength(2);
  });

  it('refuses to draw a trend through one point', async () => {
    // A flat line through a single day implies a stability nobody observed.
    render(
      <Harness
        client={clientReturning({
          '/api/v1/cost/summary': costSummaryFixture(),
          '/api/v1/cost/by-service': costByServiceFixture(),
          '/api/v1/cost/trend': {
            ...costTrendFixture(),
            data: [costTrendFixture().data[0]],
          },
        })}
      >
        <CostScreen />
      </Harness>,
    );
    await screen.findByTestId('ranked-bars');
    expect(screen.getByTestId('cost-trend-range').textContent).toMatch(/not yet a trend/);
  });

  it('ranks the services in the chart as well as in the table', async () => {
    // The chart and the table are the same rows, so they must not disagree about which
    // service is largest. A reader who spots that disagreement stops trusting both.
    renderCost();
    await screen.findByTestId('ranked-bars');
    const labels = screen.getAllByTestId('ranked-label');
    expect(labels[0]).toHaveTextContent('AmazonEC2');
    expect(screen.getByTestId('ranked-bars')).toHaveAttribute('data-provenance', 'measured');
  });

  it('has no accessibility violations', async () => {
    const { container } = renderCost();
    await screen.findByTestId('ranked-bars');
    expect(await violationsIn(container)).toEqual([]);
  });
});
