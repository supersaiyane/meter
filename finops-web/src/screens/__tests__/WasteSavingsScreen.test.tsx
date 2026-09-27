import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { WasteSavingsScreen } from '../WasteSavingsScreen';
import { WasteScoreScreen } from '../WasteScoreScreen';
import { Harness } from './Harness';
import { clientReturning } from './fixtures';
import { realizedSavingsFixture, scoresFixture } from '../../api/fixtures/waste';
import { violationsIn } from '../../components/__tests__/axe';

const SAVINGS = '/api/v1/waste/savings';
const SCORE = '/api/v1/waste/score';

function renderSavings(fixture = realizedSavingsFixture()) {
  return render(
    <Harness client={clientReturning({ [SAVINGS]: fixture })}>
      <WasteSavingsScreen />
    </Harness>,
  );
}

function renderScore(fixture = scoresFixture()) {
  return render(
    <Harness client={clientReturning({ [SCORE]: fixture })}>
      <WasteScoreScreen />
    </Harness>,
  );
}

describe('WasteSavingsScreen', () => {
  it('lists the inconclusive rows rather than hiding them', async () => {
    /**
     * The row a tool normally hides, and the one that proves the metric is
     * honest. A page of successes is the vanity number ISS-029 warns about.
     */
    renderSavings();
    const row = await screen.findByTestId('verdict-3a4b5c6d-7e8f-4a0b-9c1d-2e3f4a5b6c7d');
    expect(row).toHaveAttribute('data-verdict', 'INCONCLUSIVE');
  });

  it('gives the inconclusive row its reason, not just its label', async () => {
    renderSavings();
    expect(await screen.findByText(/cannot be told apart from a workload/)).toBeInTheDocument();
  });

  it('says an unobserved usage quantity was not published rather than showing zero', async () => {
    // A zero would say the workload went away, which is a claim nobody measured.
    renderSavings();
    expect(
      await screen.findByTestId('unobserved-3a4b5c6d-7e8f-4a0b-9c1d-2e3f4a5b6c7d'),
    ).toHaveTextContent('not published, so there is no control');
  });

  it('shows a measured usage where there is one, so the absence above means something', async () => {
    renderSavings();
    expect(
      await screen.findByTestId('usage-4b5c6d7e-8f90-4b1c-8d2e-3f4a5b6c7d8e'),
    ).toHaveTextContent('24000.0000 to 0.0000');
  });

  it('groups the money by verdict and never totals it', async () => {
    // One realized total would be added to the estimated total by the first
    // person who saw the two side by side.
    renderSavings();
    expect(await screen.findByTestId('total-VERIFIED')).toBeInTheDocument();
    expect(screen.getByTestId('total-INCONCLUSIVE')).toBeInTheDocument();
    expect(screen.getByTestId('total-REGRESSED')).toBeInTheDocument();
    expect(screen.queryByTestId('total-ALL')).not.toBeInTheDocument();
  });

  it('carries no estimated figure anywhere on the page', async () => {
    // The structural half of TASK-P3-014, at the last boundary. If this screen
    // ever grows an estimate, the sum is one subtraction away.
    const { container } = renderSavings();
    await screen.findByTestId('total-VERIFIED');
    expect(container.textContent).not.toContain('estimated');
  });

  it('says why it is empty rather than reading as nothing having worked', async () => {
    const empty = realizedSavingsFixture();
    renderSavings({ ...empty, data: { savings: [], by_verdict: {} } });
    expect(await screen.findByTestId('savings-none')).toHaveTextContent(
      'not because nothing worked',
    );
  });

  it('draws the verdicts without ever printing a share of their total', async () => {
    // The rule this whole screen exists to hold. One realized figure would be added to the
    // estimate on the recommendations screen within a week of anybody seeing both, so the total
    // is the number the product refuses to state. A chart of shares would have stated it
    // implicitly: forty percent of something is only meaningful if the something exists.
    renderSavings();
    expect(await screen.findByTestId('ranked-bars')).toBeInTheDocument();
    expect(screen.queryAllByTestId('ranked-share')).toEqual([]);
  });

  it('marks the realized chart measured, because this is where a saving is observed', async () => {
    // The one chart in the product that is not hatched. Everywhere else a saving is modelled.
    renderSavings();
    expect(await screen.findByTestId('ranked-bars')).toHaveAttribute(
      'data-provenance',
      'measured',
    );
  });

  it('has no accessibility violations', async () => {
    const { container } = renderSavings();
    await screen.findByTestId('total-VERIFIED');
    expect(await violationsIn(container)).toEqual([]);
  });
});

describe('WasteScoreScreen', () => {
  it('puts the components on the same page as the score', async () => {
    // FEAT-043's ship condition. A second call is a second thing a screen can
    // decline to make.
    renderScore();
    await screen.findByTestId('score-fake-product-a');
    expect(screen.getAllByTestId('component-waste').length).toBeGreaterThan(0);
    expect(screen.getAllByTestId('component-coverage').length).toBeGreaterThan(0);
  });

  it('says a component could not be computed rather than scoring it nought', async () => {
    renderScore();
    expect(await screen.findByTestId('component-absent-verification')).toHaveTextContent(
      'excluded from the score rather than counted as nought',
    );
  });

  it('says what the total is out of, because it is not always a hundred', async () => {
    // Fifty four out of eighty five is a different claim from fifty four out of
    // a hundred, and a reader cannot tell without being told.
    renderScore();
    const card = await screen.findByTestId('score-fake-product-a');
    expect(card.textContent).toContain('out of 85 available weight');
  });

  it('links each component to the findings that moved it', async () => {
    renderScore();
    const findings = await screen.findAllByTestId('component-findings-waste');
    const first = findings[0]?.querySelector('a');
    expect(first).toHaveAttribute(
      'href',
      '/waste?finding=2f3c1d4e-5a6b-4c7d-8e9f-0a1b2c3d4e5f',
    );
  });

  it('lists an account nobody could assess rather than leaving it out', async () => {
    // An account with no score is different from an account with a bad score,
    // and a shorter league table is not something anybody notices.
    renderScore();
    expect(await screen.findByTestId('unscored-fake-sandbox-c')).toBeInTheDocument();
    expect(screen.getByTestId('score-unscored').textContent).toContain(
      'That is different from a bad score',
    );
  });

  it('shows the worst score first', async () => {
    renderScore();
    await screen.findByTestId('score-fake-product-a');
    const cards = [...document.querySelectorAll('[data-testid^="score-fake"]')];
    expect(cards[0]).toHaveAttribute('data-testid', 'score-fake-product-a');
  });

  it('has no accessibility violations', async () => {
    const { container } = renderScore();
    await screen.findByTestId('score-fake-product-a');
    expect(await violationsIn(container)).toEqual([]);
  });
});
