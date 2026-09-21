import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { WasteScreen } from '../WasteScreen';
import { Harness } from './Harness';
import { clientReturning } from './fixtures';
import { recommendationsFixture } from '../../api/fixtures/waste';
import { violationsIn } from '../../components/__tests__/axe';

const PATH = '/api/v1/waste/recommendations';

function renderWaste(fixture = recommendationsFixture()) {
  return render(
    <Harness client={clientReturning({ [PATH]: fixture })}>
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
    const money = headers.findIndex((header) => header.includes('Monthly saving'));
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
    ).toHaveTextContent('OPEN');
  });

  it('has no accessibility violations', async () => {
    const { container } = renderWaste();
    await screen.findByText(/i-0a1b2c3d4e5f6a7b8/);
    expect(await violationsIn(container)).toEqual([]);
  });
});
