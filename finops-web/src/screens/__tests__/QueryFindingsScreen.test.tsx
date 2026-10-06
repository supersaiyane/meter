import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { byDashboard } from '../queryByDashboard';
import { QueryFindingsScreen } from '../QueryFindingsScreen';
import { Harness } from './Harness';
import { clientReturning, metaOf } from './fixtures';
import { queryFindingsFixture } from '../../api/fixtures/query';
import { violationsIn } from '../../components/__tests__/axe';

/** Live since TASK-P2-021, so the route is stubbed rather than the seam. */
function renderFindings() {
  return render(
    <Harness client={clientReturning({ '/api/v1/query/findings': queryFindingsFixture() })}>
      <QueryFindingsScreen />
    </Harness>,
  );
}

describe('query cost by dashboard', () => {
  it("sums each dashboard's queries and names the ones on no dashboard", () => {
    const findings = queryFindingsFixture().data;
    const ranked = byDashboard(findings);
    const total = findings.reduce((sum, one) => sum + Number(one.monthly_cost), 0);
    expect(ranked.reduce((sum, one) => sum + one.value, 0)).toBeCloseTo(total, 6);
    expect(ranked.map((one) => one.value)).toEqual(
      [...ranked.map((one) => one.value)].sort((left, right) => right - left),
    );
    expect(
      byDashboard(findings.slice(0, 1).map((one) => ({ ...one, dashboard_title: null }))).map(
        (one) => one.label,
      ),
    ).toEqual(['Not on a dashboard']);
  });

  it('draws what every audited query cost each day, modelled if any day was', async () => {
    const day = (run_date: string, cost: string, provenance: string) => ({
      run_date,
      cost_month_usd: cost,
      queries: 2,
      provenance,
      as_of: `${run_date}T06:00:00Z`,
      collected_at: `${run_date}T06:30:00Z`,
    });
    render(
      <Harness
        client={clientReturning({
          '/api/v1/query/findings': queryFindingsFixture(),
          '/api/v1/query/trend': {
            data: [
              day('2026-10-04', '120.00', 'measured'),
              day('2026-10-05', '90.00', 'modelled'),
              day('2026-10-06', '40.00', 'measured'),
            ],
            meta: metaOf(),
          },
        })}
      >
        <QueryFindingsScreen />
      </Harness>,
    );
    const trend = await screen.findByRole('region', { name: 'Each day' });
    const layer = await within(trend).findByTestId('area-layer');
    expect(layer.getAttribute('class')).toContain('meter-mark-modelled');
    expect(
      [...trend.querySelectorAll('table td[data-value]')].map((cell) =>
        cell.getAttribute('data-value'),
      ),
    ).toEqual(['120', '90', '40']);
  });

  it('draws them on the screen, largest first', async () => {
    renderFindings();
    const chart = await screen.findByRole('region', { name: 'Which dashboards it is on' });
    const largest = byDashboard(queryFindingsFixture().data)[0];
    expect(chart).toHaveTextContent(largest?.label ?? 'a dashboard');
  });
});

describe('QueryFindingsScreen', () => {
  it('puts the reason in a column, so it survives a screenshot', async () => {
    const table = await (renderFindings(), screen.findByRole('table'));
    expect(within(table).getByRole('columnheader', { name: /why/i })).toBeInTheDocument();
    expect(within(table).getByText(/rescans 4 GiB 8,640 times a day/)).toBeInTheDocument();
  });

  it('ranks by monthly cost, most expensive first', async () => {
    renderFindings();
    const rows = await screen.findAllByRole('row');
    expect(rows[1]).toHaveTextContent('Error rate by service');
    expect(rows[2]).toHaveTextContent('Invoice totals');
  });

  it('marks every figure in a modelled finding as modelled', async () => {
    renderFindings();
    const rows = await screen.findAllByRole('row');
    const modelled = within(rows[1] as HTMLElement).getAllByTestId('figure');
    expect(modelled.length).toBeGreaterThan(0);
    for (const figure of modelled) {
      expect(figure).toHaveAttribute('data-provenance', 'modelled');
    }
    const measured = within(rows[2] as HTMLElement).getAllByTestId('figure');
    for (const figure of measured) {
      expect(figure).toHaveAttribute('data-provenance', 'measured');
    }
  });

  it('links each finding to its own url, so it can be handed to its owner', async () => {
    renderFindings();
    const link = await screen.findByRole('link', { name: /Error rate by service/ });
    expect(link).toHaveAttribute(
      'href',
      '/govern/query-cost/findings/11111111-1111-1111-1111-111111111111',
    );
  });

  it('shows an unresolved owner as a value, not an empty cell', async () => {
    renderFindings();
    expect(await screen.findByText('unattributed')).toBeInTheDocument();
  });

  it('no longer claims to be a fixture, now that the route is live', async () => {
    // The band is driven by the same resolution that chose the source, so it
    // disappearing is the proof that this screen reads real data.
    renderFindings();
    await screen.findByRole('table');
    expect(screen.queryByTestId('fixture-band')).toBeNull();
  });

  it('has no accessibility violations', async () => {
    const { container } = renderFindings();
    await screen.findByRole('table');
    expect(await violationsIn(container)).toEqual([]);
  });
});
