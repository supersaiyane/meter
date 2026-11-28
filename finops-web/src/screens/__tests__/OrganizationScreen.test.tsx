import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { OrganizationScreen } from '../OrganizationScreen';
import { clientReturning, metaOf, TREE } from './fixtures';
import { Harness } from './Harness';

vi.mock('cytoscape', () => ({
  default: () => ({ on: () => undefined, destroy: () => undefined }),
}));

function renderScreen() {
  const client = clientReturning({ '/api/v1/org/tree': { data: TREE, meta: metaOf() } });
  return render(
    <Harness client={client}>
      <OrganizationScreen />
    </Harness>,
  );
}

describe('OrganizationScreen', () => {
  it('opens on the tree, not the graph', async () => {
    // At three hundred accounts a force directed graph is slower to read than a
    // tree, and it is the first thing a user opens. The tree is also the
    // accessible path, so it must not be the secondary one.
    renderScreen();
    await waitFor(() => {
      expect(screen.getByTestId('org-tree')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('graph')).toBeNull();
    expect(screen.getByRole('button', { name: 'Tree' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });

  it('switches to the graph on request', async () => {
    const user = userEvent.setup();
    renderScreen();
    await waitFor(() => {
      expect(screen.getByTestId('org-tree')).toBeInTheDocument();
    });
    await user.click(screen.getByRole('button', { name: 'Graph' }));
    // Loaded on demand, so the assertion waits for the chunk.
    await waitFor(() => {
      expect(screen.getByTestId('graph')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('org-tree')).toBeNull();
  });

  it('draws an unreachable branch in the tree rather than hiding it', async () => {
    renderScreen();
    await waitFor(() => {
      expect(screen.getByText('finance')).toBeInTheDocument();
    });
    expect(screen.getByText(/unreachable, outside your scope/)).toBeInTheDocument();
  });
});
