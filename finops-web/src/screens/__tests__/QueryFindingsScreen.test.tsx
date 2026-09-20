import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { QueryFindingsScreen } from '../QueryFindingsScreen';
import { Harness } from './Harness';
import { clientReturning } from './fixtures';
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
      '/governance/queries/11111111-1111-1111-1111-111111111111',
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
