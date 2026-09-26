import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import {
  graphCoverageFixture,
  inventoryRootsFixture,
  subgraphFixture,
} from '../../api/fixtures/topology';
import { violationsIn } from '../../components/__tests__/axe';
import { TopologyScreen } from '../TopologyScreen';
import { Harness } from './Harness';
import { clientReturning } from './fixtures';

vi.mock('cytoscape', () => ({
  default: () => ({ on: () => undefined, destroy: () => undefined }),
}));

const ROOT = '3f8c1a2b-4d5e-4f60-8a71-9b2c3d4e5f60';
const SUBGRAPH_PATH = `/api/v1/inventory/topology/${ROOT}?depth=2&nodes=200`;

function renderScreen() {
  const client = clientReturning({
    '/api/v1/inventory/roots': inventoryRootsFixture(),
    '/api/v1/inventory/coverage': graphCoverageFixture(),
    [SUBGRAPH_PATH]: subgraphFixture(ROOT),
  });
  return render(
    <Harness client={client} initialPath="/inventory/topology">
      <TopologyScreen />
    </Harness>,
  );
}

async function openTheMap() {
  const user = userEvent.setup();
  renderScreen();
  await waitFor(() => {
    expect(screen.getByRole('button', { name: /AWS::EC2::VPC/ })).toBeInTheDocument();
  });
  await user.click(screen.getByRole('button', { name: /AWS::EC2::VPC/ }));
  await waitFor(() => {
    expect(screen.getByTestId('topology-canvas')).toBeInTheDocument();
  });
}

describe('TopologyScreen', () => {
  it('names the unreadable slices of the estate before any map is drawn', async () => {
    // Above the graph, never in a footnote. A reader who sees the picture first has
    // already drawn a conclusion by the time they reach the small print.
    renderScreen();
    await waitFor(() => {
      expect(screen.getByTestId('estate-coverage')).toBeInTheDocument();
    });
    const banner = screen.getByTestId('estate-coverage');
    expect(banner).toHaveTextContent('fake-region-c is PARTIAL (NotOptedIn)');
    // Unread is not a synonym for partial, and the screen says which is which.
    expect(banner).toHaveTextContent('fake-region-b is UNREAD (NotYetAttempted)');
  });

  it('opens on a list of roots rather than on an empty canvas', async () => {
    renderScreen();
    await waitFor(() => {
      expect(screen.getByText('Choose a resource to map what it connects to.')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('topology-canvas')).toBeNull();
  });

  it('names a resource type the kind cannot express', async () => {
    // Ten of the generated estate's twenty four types map to OTHER, so a list showing
    // only the kind is a column of blank boxes. ISS-201.
    renderScreen();
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /AWS::EKS::Cluster/ })).toBeInTheDocument();
    });
  });

  it('says how many nodes the cap omitted, above the graph', async () => {
    await openTheMap();
    const notice = screen.getByTestId('truncation');
    expect(notice).toHaveTextContent('Showing 2 of 13 resources');
    expect(notice).toHaveTextContent('11 were omitted by the 2 node limit');
  });

  it('names the partial slice this map crossed', async () => {
    await openTheMap();
    const notice = screen.getByTestId('subgraph-coverage');
    expect(notice).toHaveTextContent('fake-product-denied');
    expect(notice).toHaveTextContent('PARTIAL (AccessDenied)');
  });

  it('carries the same nodes and edges in a table beside the map', async () => {
    // The accessible path, not the fallback. A force directed layout cannot be
    // navigated by a screen reader, so the table is what a screen reader user reads
    // and it has to hold the same facts rather than a summary of them.
    await openTheMap();
    expect(screen.getByRole('rowheader', { name: 'platform' })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: 'AWS::EC2::Subnet' })).toBeInTheDocument();
    // A null zone is regional, and a null region would be global. Neither is unknown.
    expect(screen.getByRole('cell', { name: 'regional' })).toBeInTheDocument();
  });

  it('says in the table that an edge leaves the view, not only in the drawing', async () => {
    // A dashed line means nothing to a screen reader, and the far end of a cross
    // account edge is the most interesting thing on the map.
    await openTheMap();
    expect(screen.getByText(/outside this view/)).toBeInTheDocument();
    expect(screen.getByText(/another account/)).toBeInTheDocument();
    expect(
      screen.getByRole('cell', { name: 'ec2:DescribeVpcPeeringConnections' }),
    ).toBeInTheDocument();
  });

  it('lets a keyboard reach the graph', async () => {
    // The organization map already proves this is possible, so there is no excuse for
    // a canvas a keyboard cannot land on.
    await openTheMap();
    expect(screen.getByTestId('topology-canvas')).toHaveAttribute('tabindex', '0');
    expect(screen.getByRole('img', { name: /Topology map of 2 resources/ })).toBeInTheDocument();
  });

  it('has no accessibility violations once the map is open', async () => {
    await openTheMap();
    expect(await violationsIn(document.body)).toEqual([]);
  });

  it('has no accessibility violations before a root is chosen', async () => {
    renderScreen();
    await waitFor(() => {
      expect(screen.getByTestId('estate-coverage')).toBeInTheDocument();
    });
    expect(await violationsIn(document.body)).toEqual([]);
  });
});
