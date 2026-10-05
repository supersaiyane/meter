import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { CostCommitmentsScreen } from '../CostCommitmentsScreen';
import { Harness } from './Harness';
import { clientReturning } from './fixtures';
import { costCommitmentsFixture } from '../../api/fixtures/cost';
import { violationsIn } from '../../components/__tests__/axe';

function renderCommitments(fixture = costCommitmentsFixture()) {
  return render(
    <Harness client={clientReturning({ '/api/v1/cost/commitments': fixture })}>
      <CostCommitmentsScreen />
    </Harness>,
  );
}

describe('CostCommitmentsScreen', () => {
  it('keeps the two percentages apart, each saying what it is a percentage of', async () => {
    // The whole design problem. Two percentages sit near each other and mean
    // opposite things, and a reader who conflates them draws the wrong conclusion
    // with confidence. Each heading has to name its own denominator.
    renderCommitments();
    expect(await screen.findByTestId('utilization-means')).toHaveTextContent(
      /what we paid for was used/i,
    );
    expect(screen.getByTestId('coverage-means')).toHaveTextContent(
      /estate is on a commitment/i,
    );
    expect(screen.getByTestId('utilization-heading')).toHaveTextContent(
      'Commitment utilization',
    );
    expect(screen.getByTestId('coverage-heading')).toHaveTextContent('Commitment coverage');
  });

  it('warns that a low coverage says buy whatever the utilization says', async () => {
    renderCommitments();
    expect(await screen.findByTestId('coverage-explains')).toHaveTextContent(/says buy/i);
  });

  it('shows a fully used commitment beside its barely covered service', async () => {
    // The estate this screen exists for. Reading utilization alone says the purchase
    // was correct and nothing more is needed. Reading coverage alone says buy. Both
    // are true, and the screen has to let a reader see both.
    renderCommitments();
    expect(await screen.findByTestId('utilization-fake-sp-compute')).toHaveTextContent(
      '100.0%',
    );
    expect(screen.getByTestId('coverage-AmazonEC2')).toHaveTextContent('40.4%');
  });

  it('says a commitment has not started rather than showing it as nothing used', async () => {
    // Zero percent would say the money was wasted. It has not started.
    renderCommitments();
    expect(await screen.findByTestId('utilization-fake-sp-queued')).toHaveTextContent(
      'not started',
    );
    expect(screen.getByTestId('utilization-fake-sp-queued')).not.toHaveTextContent('0.0%');
  });

  it('shows an eligible and uncovered service as a real zero', async () => {
    // Distinct from the sentence above. Zero here says the estate is uncovered and
    // somebody should buy, which is an action.
    renderCommitments();
    expect(await screen.findByTestId('coverage-AWSLambda')).toHaveTextContent('0.0%');
  });

  it('reports an expired commitment rather than dropping it', async () => {
    // The money was spent, and the coverage gap the expiry leaves is the finding.
    renderCommitments();
    const row = (await screen.findByText('fake-sp-expired')).closest('tr');
    expect(row?.textContent).toContain('EXPIRED');
  });

  it('puts the unused money at the top, in money', async () => {
    // A percentage alone does not say whether it is worth a morning.
    renderCommitments();
    const waste = await screen.findByTestId('commitment-waste');
    expect(waste.textContent).toMatch(/367\.46/);
  });

  it('ranks the most wasted commitment first', async () => {
    renderCommitments();
    await screen.findByText('fake-ri-rds');
    const ids = [...document.querySelectorAll('tbody tr')]
      .map((row) => row.querySelector('td')?.textContent)
      .filter((text): text is string => typeof text === 'string');
    expect(ids[0]).toBe('fake-ri-rds');
  });

  it('says the figures are payer wide and cannot be narrowed', async () => {
    // A reader whose scope is two accounts would otherwise wonder why these numbers
    // are larger than the ones on their spend screen.
    renderCommitments();
    expect(await screen.findByTestId('commitment-scope-note')).toHaveTextContent(
      /whole payer/i,
    );
  });

  it('never renders a coverage figure inside a commitment row', async () => {
    // A covered dollar cannot be attributed to one of several overlapping plans, so
    // a coverage number in a commitment row would be an invention.
    renderCommitments();
    const row = (await screen.findByText('fake-sp-compute')).closest('tr');
    expect(row?.querySelector('[data-testid^="coverage-"]')).toBeNull();
  });

  it('has no accessibility violations', async () => {
    const { container } = renderCommitments();
    await screen.findByText('fake-ri-rds');
    expect(await violationsIn(container)).toEqual([]);
  });

  describe('the gap as an action, FEAT-055', () => {
    it('says what to do about the gap, not only how big it is', async () => {
      // The coverage table answers how much is uncovered. This answers what to do about it,
      // which is the difference between a fact nobody owns and a decision somebody works.
      renderCommitments();
      const actions = await screen.findByTestId('actions');
      expect(actions).toHaveTextContent('AmazonEC2');
      expect(actions).toHaveTextContent('Savings Plan');
    });

    it('publishes the usage floor, which is what being wrong looks like', async () => {
      // The figure a coverage chart cannot show and the reason this is a decision. A commitment
      // obligates its whole term whether or not the usage continues, so a row with the saving
      // and not the floor would be recommending a multi year obligation while withholding the
      // risk.
      renderCommitments();
      const actions = await screen.findByTestId('actions');
      expect(actions).toHaveTextContent('above 70.0 percent of today');
      expect(actions).toHaveTextContent('for 12 months');
    });

    it('calls a commitment permanent, because it cannot be handed back', async () => {
      // Through the same module the waste screen and the home panel use, so a reader is not
      // told a change is permanent in one place and reversible in another. Nothing stops to buy
      // a commitment, which is exactly why it reads as safe.
      renderCommitments();
      expect(await screen.findByTestId('actions')).toHaveTextContent('permanent');
    });

    it('marks the saving modelled, never measured', async () => {
      // The discount is an assumption about a price nobody has been quoted. The utilization
      // figures on the same screen are measured, so rendering the two identically would invite
      // a reader to treat the estimate as a fact.
      renderCommitments();
      const actions = await screen.findByTestId('actions');
      for (const figure of within(actions).getAllByTestId('figure')) {
        expect(figure).toHaveAttribute('data-provenance', 'modelled');
      }
    });
  });
});
