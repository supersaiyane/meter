import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ContainerCostScreen } from '../ContainerCostScreen';
import { Harness } from './Harness';
import { clientReturning } from './fixtures';
import { containerCostFixture } from '../../api/fixtures/containers';
import { violationsIn } from '../../components/__tests__/axe';

/**
 * FEAT-035. A cluster's cost, and the sum a reader can check.
 *
 * The failure guarded is a breakdown that does not reconcile: workloads that add to less or
 * more than the cluster they sit in, which is money invented or lost. The screen shows the
 * sum, so the tests assert the sum, from the fixture's own figures rather than from literals.
 */

const PATH = '/api/v1/cost/containers';

function renderScreen() {
  return render(
    <Harness client={clientReturning({ [PATH]: containerCostFixture() })}>
      <ContainerCostScreen />
    </Harness>,
  );
}

describe('ContainerCostScreen', () => {
  it('shows each cluster with its total, its share and its remainder', async () => {
    renderScreen();
    const sections = await screen.findAllByTestId('container-cost-cluster');
    expect(sections).toHaveLength(containerCostFixture().data.clusters.length);
    for (const section of sections) {
      const line = within(section).getByTestId('cost-reconciliation');
      expect(within(line).getByTestId('cost-allocated')).toBeInTheDocument();
      expect(within(line).getByTestId('cost-unallocated')).toBeInTheDocument();
      expect(within(line).getByTestId('cost-total')).toBeInTheDocument();
    }
  });

  it('reconciles: allocated plus unallocated is the total, and the rows are the allocated', () => {
    // Against the data the screen renders, so the claim the screen makes visibly is true.
    for (const cluster of containerCostFixture().data.clusters) {
      const allocated = Number(cluster.allocated);
      const unallocated = Number(cluster.unallocated);
      expect(allocated + unallocated).toBeCloseTo(Number(cluster.total), 2);
      const rows = cluster.workloads.reduce((sum, row) => sum + Number(row.cost), 0);
      expect(rows).toBeCloseTo(allocated, 2);
    }
  });

  it('labels every figure measured, never modelled', async () => {
    renderScreen();
    await screen.findAllByTestId('container-cost-cluster');
    const figures = screen.getAllByTestId('figure');
    expect(figures.length).toBeGreaterThan(0);
    for (const figure of figures) {
      expect(figure).toHaveAttribute('data-provenance', 'measured');
    }
  });

  it('states how many clusters can be broken down', async () => {
    renderScreen();
    const ratio = await screen.findByTestId('container-cost-ratio');
    const { measured_count, found_count } = containerCostFixture().data;
    expect(ratio.textContent).toContain(`${String(measured_count)} of ${String(found_count)}`);
  });
});

describe('accessibility', () => {
  it('has no violations', async () => {
    const { container } = renderScreen();
    await screen.findAllByTestId('container-cost-cluster');
    expect(await violationsIn(container)).toEqual([]);
  });
});
