import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { WasteScreen } from '../WasteScreen';
import { Harness } from './Harness';
import { clientReturning } from './fixtures';
import { recommendationsFixture, refusalsFixture } from '../../api/fixtures/waste';
import { violationsIn } from '../../components/__tests__/axe';

const PATH = '/api/v1/waste/recommendations';

function renderWaste(fixture = recommendationsFixture()) {
  return render(
    <Harness
      client={clientReturning({
        [PATH]: fixture,
        // FEAT-062. The screen asks for two things now, and a screen whose second request has
        // no stub renders without that section rather than failing, which is correct behaviour
        // and would make every assertion about it pass vacuously.
        '/api/v1/waste/refusals': refusalsFixture(),
      })}
    >
      <WasteScreen />
    </Harness>,
  );
}

describe('WasteScreen', () => {
  it('does not put the money next to the confidence', async () => {
    /**
     * The one layout rule this screen exists to keep. A reader comparing the two
     * side by side reads confidence as a discount on the money, which it is not:
     * a large finding on three weeks of data is worth its full value if it is
     * right, and the confidence says how likely that is.
     */
    renderWaste();
    await screen.findByText(/i-0a1b2c3d4e5f6a7b8/);
    const headers = [...document.querySelectorAll('thead th')].map((cell) => cell.textContent);
    const money = headers.findIndex((header) => header.includes('Estimated monthly savings'));
    const confidence = headers.findIndex((header) => header.includes('Confidence'));
    expect(money).toBeGreaterThanOrEqual(0);
    expect(confidence).toBeGreaterThanOrEqual(0);
    expect(Math.abs(money - confidence)).toBeGreaterThan(1);
  });

  it('labels the estimate as modelled rather than measured', async () => {
    // It is arithmetic over metrics, not a figure anybody has seen on a bill.
    // The realized savings screen is where measured money lives.
    renderWaste();
    await screen.findByText(/i-0a1b2c3d4e5f6a7b8/);
    const figures = [...document.querySelectorAll('[data-testid="figure"]')];
    expect(figures.length).toBeGreaterThan(0);
    expect(figures.some((figure) => figure.textContent.includes('modelled'))).toBe(true);
    expect(figures.some((figure) => figure.textContent.includes('measured'))).toBe(false);
  });

  it('says a recommendation has no owner rather than leaving a blank cell', async () => {
    // ISS-021: an unowned finding is never fixed, and a blank cell is the least
    // noticeable way to render the fact most likely to kill the work.
    renderWaste();
    expect(
      await screen.findByTestId('unowned-2f3c1d4e-5a6b-4c7d-8e9f-0a1b2c3d4e5f'),
    ).toHaveTextContent('nobody yet');
  });

  it('names whom an unowned resource is tagged to, and suggests nobody it was not told', async () => {
    // ISS-021's first slice: the resource's team tag says whom to ask, and is never an owner.
    renderWaste();
    expect(
      await screen.findByTestId('suggested-owner-2f3c1d4e-5a6b-4c7d-8e9f-0a1b2c3d4e5f'),
    ).toHaveTextContent('its team tag says platform');
    expect(
      screen.getByTestId('unowned-7a8b9c0d-1e2f-4a3b-8c4d-5e6f7a8b9c0d'),
    ).toHaveTextContent('nobody yet');
    expect(
      screen.queryByTestId('suggested-owner-7a8b9c0d-1e2f-4a3b-8c4d-5e6f7a8b9c0d'),
    ).toBeNull();
  });

  it('counts the unowned findings above the table', async () => {
    renderWaste();
    expect(await screen.findByTestId('waste-unowned-count')).toHaveTextContent(
      'An unowned finding is one nobody is going to fix',
    );
  });

  it('says so when everything has an owner rather than showing nothing', async () => {
    const owned = recommendationsFixture();
    renderWaste({
      ...owned,
      data: {
        recommendations: owned.data.recommendations.filter((row) => row.owner !== null),
        unowned: 0,
      },
    });
    expect(await screen.findByTestId('waste-all-owned')).toBeInTheDocument();
  });

  it('shows the confidence with the days it rests on', async () => {
    // "LOW" on its own is a label. "LOW on 15 days" is something a reader can
    // argue with, which is the difference between the two.
    renderWaste();
    expect(
      await screen.findByTestId('confidence-2f3c1d4e-5a6b-4c7d-8e9f-0a1b2c3d4e5f'),
    ).toHaveTextContent('LOW on 15 days');
  });

  it('renders the working whole', async () => {
    renderWaste();
    expect(
      await screen.findByText(/p99 CPU of 11.4 percent against 4 vCPU/),
    ).toBeInTheDocument();
  });

  it('shows the lifecycle, because a finding nobody moved is the common case', async () => {
    renderWaste();
    expect(
      await screen.findByTestId('lifecycle-2f3c1d4e-5a6b-4c7d-8e9f-0a1b2c3d4e5f'),
    ).toHaveTextContent('Open');
  });

  it('charts only the waste that is still open', async () => {
    // The rule that can be wrong here. The fixture's Graviton candidate is ACCEPTED and its
    // unattached volume is DONE, so two of its four rows are work. Charting all four would draw
    // money that is not available, and the picture would grow every time somebody fixed
    // something, which is the wrong direction for a chart about waste.
    renderWaste();
    const rows = await screen.findAllByTestId('ranked-label');
    expect(rows.map((row) => row.textContent)).toEqual([
      'Rightsizing',
      'Alarm with insufficient data',
    ]);
  });

  it('hatches the chart, because no saving on it has been measured', async () => {
    renderWaste();
    expect(await screen.findByTestId('ranked-bars')).toHaveAttribute(
      'data-provenance',
      'modelled',
    );
  });

  it('has no accessibility violations', async () => {
    const { container } = renderWaste();
    await screen.findByText(/i-0a1b2c3d4e5f6a7b8/);
    expect(await violationsIn(container)).toEqual([]);
  });

  it('shows what the rules looked at and left alone, beside the list and not in it', async () => {
    // FEAT-062, ADR-0027. A service that never appears in the waste list is otherwise
    // indistinguishable from one nobody examined, and those are different facts.
    renderWaste();
    expect(await screen.findByTestId('refusals')).toBeInTheDocument();
    expect(screen.getByTestId('refusals-count')).toHaveTextContent('4 resources were examined');
  });

  it('gives a refusal no money and no severity', async () => {
    // The property that kept this out of the recommendation table. ADR-0016 ranks that list by
    // money, so a zero there reads as the least valuable action rather than the absence of one.
    renderWaste();
    const table = await screen.findByTestId('refusals-table');
    expect(table).not.toHaveTextContent('$');
    expect(within(table).queryAllByTestId('severity')).toEqual([]);
  });

  it('orders a refusal by what the judgement rests on', async () => {
    // It cannot be ranked by money, so the useful order is observation: four days is worth
    // questioning and ninety is worth relying on.
    renderWaste();
    const table = await screen.findByTestId('refusals-table');
    const first = within(table).getAllByRole('row')[1];
    expect(first).toHaveTextContent('4 days');
  });

  it('keeps the reason whole, because a shortened one cannot be argued with', async () => {
    renderWaste();
    const table = await screen.findByTestId('refusals-table');
    expect(table).toHaveTextContent(
      '94 percent memory ceiling, so this is memory bound and a CPU rule must not shrink it',
    );
  });
});

describe('WasteScreen, one finding from the FinOps Score', () => {
  const FINDING = '2f3c1d4e-5a6b-4c7d-8e9f-0a1b2c3d4e5f';

  it('lands on the finding a FinOps Score link names, and says so', async () => {
    render(
      <Harness
        initialPath={`/optimize?finding=${FINDING}`}
        client={clientReturning({
          [PATH]: recommendationsFixture(),
          '/api/v1/waste/refusals': refusalsFixture(),
        })}
      >
        <WasteScreen />
      </Harness>,
    );
    expect(await screen.findByTestId(`lifecycle-${FINDING}`)).toBeInTheDocument();
    expect(screen.queryByTestId('lifecycle-3a4b5c6d-7e8f-4a0b-9c1d-2e3f4a5b6c7d')).toBeNull();
    const note = screen.getByTestId('filtered-to-finding');
    expect(note).toHaveTextContent(FINDING);
    expect(
      within(note).getByRole('link', { name: 'Show every recommendation' }),
    ).toHaveAttribute('href', '/optimize');
  });
});

describe('owner suggestions, TASK-P11-005', () => {
  it('lists every source under the owner a person assigned, strongest first', async () => {
    renderWaste();
    const listed = await screen.findByTestId(
      'owner-suggestions-3a4b5c6d-7e8f-4a0b-9c1d-2e3f4a5b6c7d',
    );
    expect(
      within(listed)
        .getAllByRole('listitem')
        .map((item) => item.textContent),
    ).toEqual([
      "payments, the catalogue's checkout application",
      'deploy-pipeline, the pipeline that created it',
    ]);
  });

  it('says an unowned resource older than the history was created before it', async () => {
    renderWaste();
    expect(
      await screen.findByTestId('created-before-7a8b9c0d-1e2f-4a3b-8c4d-5e6f7a8b9c0d'),
    ).toHaveTextContent("created before CloudTrail's 90 days, which begin 2026-05-26");
    expect(
      screen.getByTestId('unowned-7a8b9c0d-1e2f-4a3b-8c4d-5e6f7a8b9c0d'),
    ).toHaveTextContent('nobody yet');
  });
});
