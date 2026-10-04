import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ContainerWasteScreen } from '../ContainerWasteScreen';
import { Harness } from './Harness';
import { clientReturning } from './fixtures';
import { containerCostFixture, containerWasteFixture } from '../../api/fixtures/containers';
import { violationsIn } from '../../components/__tests__/axe';

/**
 * FEAT-036. Request against use, and the cluster that cannot state it.
 *
 * Two failures are guarded. The first is the efficiency percentage every dashboard reaches
 * for, which hides whether a namespace is over requesting or idle. The second is the cluster
 * without enhanced observability vanishing, or rendering with empty request cells a reader
 * takes for zeros. The unmeasurable cluster is found from the fixture by what it is, never by
 * its name, so this cannot pass by testing the wrong row.
 */

const PATH = '/api/v1/waste/containers';
const COST_PATH = '/api/v1/cost/containers';

function renderScreen() {
  return render(
    <Harness
      client={clientReturning({
        [PATH]: containerWasteFixture(),
        [COST_PATH]: containerCostFixture(),
      })}
    >
      <ContainerWasteScreen />
    </Harness>,
  );
}

function unmeasurableName(): string {
  const found = containerWasteFixture().data.clusters.find((c) => !c.enhanced_observability);
  if (found === undefined) {
    throw new Error('the fixture has no cluster without requests, so nothing here is tested');
  }
  return found.cluster_name;
}

function clusterSection(name: string): HTMLElement {
  const sections = screen.getAllByTestId('container-cluster');
  const match = sections.find((section) =>
    within(section).getByTestId('container-cluster-name').textContent.includes(name),
  );
  if (match === undefined) {
    throw new Error(`no section for ${name}`);
  }
  return match;
}

describe('ContainerWasteScreen', () => {
  it('lists every cluster, the one without requests included', async () => {
    renderScreen();
    const sections = await screen.findAllByTestId('container-cluster');
    expect(sections).toHaveLength(containerWasteFixture().data.clusters.length);
  });

  it('shows request and use as separate columns and never one percentage', async () => {
    renderScreen();
    const tables = await screen.findAllByTestId('container-requests');
    for (const table of tables) {
      expect(within(table).getAllByTestId('cpu-requested').length).toBeGreaterThan(0);
      expect(within(table).getAllByTestId('cpu-used').length).toBeGreaterThan(0);
      // The shape rules out a ratio arriving as 19%, 0.19 or a bar.
      expect(table.textContent).not.toMatch(/%|percent of|efficiency/i);
    }
  });

  it('gives the unmeasurable cluster its cost and its reason, and no request column', async () => {
    renderScreen();
    await screen.findAllByTestId('container-cluster');
    const section = clusterSection(unmeasurableName());
    expect(section).toHaveAttribute('data-measurable', 'false');
    // With its cost, measured.
    const cost = within(section).getByTestId('container-cluster-cost');
    expect(within(cost).getByTestId('figure')).toHaveAttribute('data-provenance', 'measured');
    // Naming the reason.
    expect(within(section).getByTestId('container-reason').textContent).toMatch(/enhanced/i);
    // Without its utilization: no request cell exists, so none can read as zero.
    expect(within(section).queryAllByTestId('cpu-requested')).toHaveLength(0);
    expect(within(section).queryAllByTestId('container-requests')).toHaveLength(0);
  });

  it('says an unobserved kill could not be observed rather than saying no', async () => {
    renderScreen();
    await screen.findAllByTestId('container-cluster');
    const unobserved = screen
      .getAllByTestId('container-oom')
      .filter((cell) => cell.getAttribute('data-oom') === 'UNOBSERVED');
    expect(unobserved.length).toBeGreaterThan(0);
    for (const cell of unobserved) {
      expect(cell.textContent).toBe('could not be observed');
    }
  });

  it('states the ratio rather than leaving a reader to count', async () => {
    renderScreen();
    const ratio = await screen.findByTestId('containers-ratio');
    const { measured_count, found_count } = containerWasteFixture().data;
    expect(ratio.textContent).toContain(`${String(measured_count)} of ${String(found_count)}`);
  });
});

describe('accessibility', () => {
  it('has no violations', async () => {
    const { container } = renderScreen();
    await screen.findAllByTestId('container-cluster');
    expect(await violationsIn(container)).toEqual([]);
  });
});
