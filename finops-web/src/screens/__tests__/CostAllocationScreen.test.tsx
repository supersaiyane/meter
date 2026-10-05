import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { CostAllocationScreen } from '../CostAllocationScreen';
import { Harness } from './Harness';
import { clientReturning } from './fixtures';
import { costAllocationFixture } from '../../api/fixtures/cost';
import { violationsIn } from '../../components/__tests__/axe';

function renderAllocation(fixture = costAllocationFixture()) {
  return render(
    <Harness
      client={clientReturning({
        // The tag is part of the request, so it is part of the key the stub
        // matches on. Two groupings of one period by different keys are
        // different answers and must not share a stub any more than they share
        // a cache entry.
        '/api/v1/cost/allocation?tag=team': fixture,
      })}
    >
      <CostAllocationScreen />
    </Harness>,
  );
}

describe('CostAllocationScreen', () => {
  it('renders what nobody tagged as a row of its own', async () => {
    // The whole point of the screen. An allocation view that drops what it
    // cannot attribute reports a smaller estate than exists.
    renderAllocation();
    expect(await screen.findByTestId('allocation-unallocated')).toBeInTheDocument();
  });

  it('says how much of the period is unattributed', async () => {
    // A percentage, because the absolute number means nothing without the
    // total beside it and a reader should not have to do the division.
    renderAllocation();
    const gap = await screen.findByTestId('allocation-gap');
    expect(gap.textContent).toMatch(/percent of this period is not attributed/);
  });

  it('says so plainly when everything is attributed', async () => {
    const tidy = costAllocationFixture();
    const complete = {
      ...tidy,
      data: tidy.data.filter((row) => row.name !== 'unallocated'),
    };
    renderAllocation(complete);
    const gap = await screen.findByTestId('allocation-gap');
    expect(gap.textContent).toMatch(/Every charge in this period carries/);
  });

  it('offers a tag key to group by, with no silent default at the API', async () => {
    renderAllocation();
    expect(await screen.findByTestId('allocation-key')).toBeInTheDocument();
  });

  it('shows every figure as measured', async () => {
    renderAllocation();
    await screen.findByTestId('ranked-bars');
    const figures = document.querySelectorAll('[data-testid="figure"]');
    expect(figures.length).toBeGreaterThan(0);
    for (const figure of figures) {
      expect(figure.getAttribute('data-provenance')).toBe('measured');
    }
  });

  it('has no accessibility violations', async () => {
    const { container } = renderAllocation();
    await screen.findByTestId('ranked-bars');
    expect(await violationsIn(container)).toEqual([]);
  });
});

describe('CostAllocationScreen, the key in the address', () => {
  it('groups by the tag key the address names, and asks for that one', async () => {
    render(
      <Harness
        initialPath="/analyze/allocation?tag=service"
        client={clientReturning({
          '/api/v1/cost/allocation?tag=service': costAllocationFixture(),
        })}
      >
        <CostAllocationScreen />
      </Harness>,
    );
    expect(await screen.findByRole('combobox')).toHaveValue('service');
  });
});
