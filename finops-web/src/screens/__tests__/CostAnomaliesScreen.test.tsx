import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { CostAnomaliesScreen } from '../CostAnomaliesScreen';
import { Harness } from './Harness';
import { clientReturning } from './fixtures';
import { costAnomaliesFixture } from '../../api/fixtures/cost';
import { violationsIn } from '../../components/__tests__/axe';

function renderAnomalies(fixture = costAnomaliesFixture()) {
  return render(
    <Harness client={clientReturning({ '/api/v1/cost/anomalies': fixture })}>
      <CostAnomaliesScreen />
    </Harness>,
  );
}

describe('CostAnomaliesScreen', () => {
  it('says an estate is too young to judge rather than saying it is fine', async () => {
    // The hardest thing on this screen. Four days of history is not an estate
    // with no anomalies, and a reader who takes the silence for safety acts on
    // it.
    const young = costAnomaliesFixture();
    renderAnomalies({
      ...young,
      data: { ...young.data, anomalies: [], days_collected: 4 },
    });
    expect(await screen.findByTestId('anomaly-too-young')).toBeInTheDocument();
    expect(screen.queryByTestId('anomaly-none')).not.toBeInTheDocument();
  });

  it('says an estate with enough history and nothing wrong is behaving', async () => {
    const quiet = costAnomaliesFixture();
    renderAnomalies({ ...quiet, data: { ...quiet.data, anomalies: [] } });
    expect(await screen.findByTestId('anomaly-none')).toBeInTheDocument();
    expect(screen.queryByTestId('anomaly-too-young')).not.toBeInTheDocument();
  });

  it('shows the money, not only a ratio', async () => {
    // Somebody has to know the money before they can decide whether to care.
    renderAnomalies();
    await screen.findByText(/AmazonEC2/);
    const figures = document.querySelectorAll('[data-testid="figure"]');
    expect(figures.length).toBeGreaterThan(0);
  });

  it('shows the baseline, so the verdict can be argued with', async () => {
    renderAnomalies();
    const row = (await screen.findByText(/AmazonEC2/)).closest('tr');
    expect(row?.textContent).toContain('191.44');
  });

  it('renders the working whole', async () => {
    renderAnomalies();
    expect(
      await screen.findByText('+550.75 against a usual 191.44, which is 9.2 deviations out'),
    ).toBeInTheDocument();
  });

  it('survives a null deviation rather than printing a zero', async () => {
    // A perfectly steady baseline has no answer to "how many deviations", and
    // rendering nought would be a confidence the detector does not have.
    renderAnomalies();
    const row = (await screen.findByText(/AmazonCloudWatch/)).closest('tr');
    expect(row?.textContent).toContain('had not moved');
  });

  it('puts the biggest move first', async () => {
    renderAnomalies();
    await screen.findByText(/AmazonEC2/);
    const rows = [...document.querySelectorAll('tbody tr')];
    expect(rows[0]?.textContent).toContain('AmazonEC2');
  });

  it('has no accessibility violations', async () => {
    const { container } = renderAnomalies();
    await screen.findByText(/AmazonEC2/);
    expect(await violationsIn(container)).toEqual([]);
  });
});
