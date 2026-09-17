import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { QuerySurfacesScreen } from '../QuerySurfacesScreen';
import { Harness } from './Harness';
import { clientReturning } from './fixtures';
import { violationsIn } from '../../components/__tests__/axe';

function renderSurfaces() {
  return render(
    <Harness client={clientReturning({})}>
      <QuerySurfacesScreen />
    </Harness>,
  );
}

function rowFor(name: string): HTMLElement {
  const row = screen.getByText(name).closest('tr');
  if (row === null) {
    throw new Error(`no row for ${name}`);
  }
  return row;
}

describe('QuerySurfacesScreen', () => {
  it('lists an instance it could not reach', async () => {
    // Omitting it would make the findings list look complete when it is not.
    renderSurfaces();
    expect(await screen.findByText('meter-prod-eu-west-1')).toBeInTheDocument();
  });

  it('shows an unreachable query count as its cause, never as zero', async () => {
    renderSurfaces();
    await screen.findByText('meter-prod-eu-west-1');
    const row = rowFor('meter-prod-eu-west-1');
    expect(within(row).getByText('ACCESS DENIED')).toBeInTheDocument();
    expect(within(row).queryByText('0')).toBeNull();
  });

  it('still renders a genuine zero as zero', async () => {
    // The whole point of the row above is that it does not compete with this
    // one. An instance that was read and holds nothing says zero.
    renderSurfaces();
    await screen.findByText('meter-staging-eu-west-2');
    const row = rowFor('meter-staging-eu-west-2');
    expect(within(row).getByText('0')).toBeInTheDocument();
  });

  it('says so while it is running on a fixture', async () => {
    renderSurfaces();
    expect(await screen.findByTestId('fixture-band')).toBeInTheDocument();
  });

  it('has no accessibility violations', async () => {
    const { container } = renderSurfaces();
    await screen.findByRole('table');
    expect(await violationsIn(container)).toEqual([]);
  });
});
