import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ClustersScreen } from '../ClustersScreen';
import { Harness } from './Harness';
import { clientReturning } from './fixtures';
import { clustersFixture } from '../../api/fixtures/containers';
import { violationsIn } from '../../components/__tests__/axe';

/**
 * Clusters, Spot ratio and bin packing. Every missing figure has to say why, and the two
 * reasons a figure can be missing are different sentences: a fleet nobody could read, and a
 * Fargate cluster with no fleet at all. Each row is found by what it is, never by its name.
 */

const PATH = '/api/v1/inventory/clusters';

/** A row by position, refusing rather than passing a missing one into an assertion. */
function rowAt(rows: readonly HTMLElement[], index: number): HTMLElement {
  const row = rows[index];
  if (row === undefined) {
    throw new Error(
      `no cluster row at ${String(index)}, so the fixture and the screen disagree`,
    );
  }
  return row;
}

function renderScreen() {
  return render(
    <Harness client={clientReturning({ [PATH]: clustersFixture() })}>
      <ClustersScreen />
    </Harness>,
  );
}

describe('ClustersScreen', () => {
  it('lists every cluster, the ones with nothing measured included', async () => {
    renderScreen();
    const rows = await screen.findAllByTestId('cluster-row');
    expect(rows).toHaveLength(clustersFixture().data.clusters.length);
  });

  it('shows Spot ratio and bin packing per cluster where the fleet is readable', async () => {
    renderScreen();
    const rows = await screen.findAllByTestId('cluster-row');
    // One fixture instance: each call builds a new object, so an index taken from one call
    // and looked up in another is always minus one.
    const index = clustersFixture().data.clusters.findIndex(
      (c) => c.packing_efficiency !== null,
    );
    expect(index).toBeGreaterThanOrEqual(0);
    const row = rowAt(rows, index);
    expect(
      within(within(row).getByTestId('cluster-spot')).getByTestId('percent-cell'),
    ).toBeInTheDocument();
    expect(
      within(within(row).getByTestId('cluster-packing')).getByTestId('percent-cell'),
    ).toBeInTheDocument();
  });

  it('says a Fargate cluster has no fleet rather than drawing an empty bar', async () => {
    renderScreen();
    const rows = await screen.findAllByTestId('cluster-row');
    const fargate = rows.filter((row) => row.getAttribute('data-platform') === 'ECS');
    expect(fargate.length).toBeGreaterThan(0);
    for (const row of fargate) {
      expect(within(row).queryAllByTestId('percent-cell')).toHaveLength(0);
      expect(within(row).getByTestId('cluster-packing').textContent).toMatch(/without nodes/);
    }
  });

  it('names why packing is missing on a cluster whose requests are unreadable', async () => {
    renderScreen();
    const rows = await screen.findAllByTestId('cluster-row');
    const unreadable = clustersFixture().data.clusters.findIndex(
      (c) => c.platform !== 'ECS' && c.packing_efficiency === null,
    );
    expect(unreadable).toBeGreaterThanOrEqual(0);
    const packing = within(rowAt(rows, unreadable)).getByTestId('cluster-packing');
    expect(within(packing).getByTestId('percent-absent').textContent).toMatch(/enhanced/i);
  });
});

describe('accessibility', () => {
  it('has no violations', async () => {
    const { container } = renderScreen();
    await screen.findAllByTestId('cluster-row');
    expect(await violationsIn(container)).toEqual([]);
  });
});
