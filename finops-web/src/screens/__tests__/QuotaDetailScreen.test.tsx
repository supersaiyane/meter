import { render, screen, within } from '@testing-library/react';
import { Route, Routes } from 'react-router';
import { describe, expect, it } from 'vitest';

import { QuotaDetailScreen } from '../QuotaDetailScreen';
import { Harness } from './Harness';
import { clientReturning } from './fixtures';
import { quotaDetailFixture } from '../../api/fixtures/quotas';
import type { ApiEnvelope, ApiQuotaDetail } from '../../api/types';
import { violationsIn } from '../../components/__tests__/axe';

/**
 * FEAT-034, and the case that carries this file is the sentence.
 *
 * Meter drafts a quota increase and never submits it, which is constraint 6 and P5 spec section
 * 6. That decision is worth nothing to a reader who does not know it, and the moment they form
 * an expectation about what happens next is the moment they see the command. So the sentence
 * has to be beside the command rather than in a footnote, and this file asserts the proximity
 * as well as the presence.
 *
 * The second case is the refusal. Four reasons and each is a different thing to do, so a screen
 * rendering only the drafts would leave a reader wondering whether the rest were forgotten.
 */

const PATH = '/api/v1/governance/quotas/ec2/L-1216C47A';
const ROUTE = '/governance/quotas/ec2/L-1216C47A';

function renderDetail(fixture: ApiEnvelope<ApiQuotaDetail> = quotaDetailFixture()) {
  // Inside a real Route, because `useParams` resolves against a match and not against the
  // path: rendered bare it returns nothing, the hook asks for a quota with no code, and every
  // assertion below fails for a reason that has nothing to do with the screen.
  return render(
    <Harness client={clientReturning({ [PATH]: fixture })} initialPath={ROUTE}>
      <Routes>
        <Route
          path="/governance/quotas/:serviceCode/:quotaCode"
          element={<QuotaDetailScreen />}
        />
      </Routes>
    </Harness>,
  );
}

function withoutDrafts(): ApiEnvelope<ApiQuotaDetail> {
  const fixture = quotaDetailFixture();
  return { ...fixture, data: { ...fixture.data, drafts: [], draft_refusals: [] } };
}

describe('the draft', () => {
  it('shows the current limit, the observed peak and the suggested value', async () => {
    // All three, because a suggested value alone is a number a reader cannot check.
    renderDetail();
    const figures = await screen.findByTestId('draft-figures');
    expect(figures.textContent).toContain('320');
    expect(figures.textContent).toContain('307');
    expect(figures.textContent).toContain('520');
  });

  it('publishes the working so a reader disputes the target and not the figure', async () => {
    renderDetail();
    const working = await screen.findByTestId('draft-working');
    expect(working.textContent).toContain('40 percent');
    expect(working.textContent).toContain('rounded up');
  });

  it('says Meter will not submit it, beside the command rather than in a footnote', async () => {
    // The proximity is the assertion. A sentence elsewhere on the page is one a reader forms
    // their expectation without, and the expectation is formed at the command.
    renderDetail();
    const draft = await screen.findByTestId('quota-draft');
    const notice = within(draft).getByTestId('draft-not-submitted');
    expect(notice.textContent).toContain('will not submit');
    expect(within(draft).getByTestId('draft-command')).toBeTruthy();
  });

  it('gives a console link and a command that are both exact', async () => {
    renderDetail();
    const link = await screen.findByTestId('draft-console');
    expect(link.getAttribute('href')).toContain('console.aws.amazon.com/servicequotas');
    const command = screen.getByTestId('draft-command');
    expect(command.textContent).toContain('aws service-quotas request-service-quota-increase');
    expect(command.textContent).toContain('--desired-value 520');
  });

  it('never names the API Meter does not call', async () => {
    // The CLI form is a command for a person. The PascalCase name is a call this product makes,
    // and it must not reach a screen either: a reader copying it would be looking for an SDK.
    const { container } = renderDetail();
    await screen.findByTestId('draft-command');
    expect(container.textContent).not.toContain('RequestServiceQuotaIncrease');
  });
});

describe('the refusal to draft', () => {
  it('is shown as plainly as a draft, with its reason', async () => {
    renderDetail();
    const refused = await screen.findByTestId('quota-draft-refused');
    expect(within(refused).getByTestId('draft-refused-reason').textContent).toContain(
      'not short of',
    );
  });

  it('says nothing was collected rather than showing an empty draft', async () => {
    // The state a screen is most likely to render as a draft for nothing.
    renderDetail(withoutDrafts());
    const absent = await screen.findByTestId('quota-no-drafts');
    expect(absent.getAttribute('data-state')).toBe('never-collected');
    expect(screen.queryAllByTestId('quota-draft')).toHaveLength(0);
  });
});

describe('the requests', () => {
  it('shows when each status changed and not only what it is now', async () => {
    // The current status can say a request was approved and not when, and how long an increase
    // has been waiting is the question FEAT-034 exists for.
    renderDetail();
    const history = await screen.findByTestId('request-history');
    expect(history.textContent).toContain('2026-09-18');
    expect(history.textContent).toContain('2026-09-20');
  });

  it('says a request came from outside Meter', async () => {
    renderDetail();
    const notice = await screen.findByTestId('request-not-ours');
    expect(notice.textContent).toContain('outside Meter');
  });
});

describe('accessibility', () => {
  it('has no violations', async () => {
    const { container } = renderDetail();
    await screen.findByTestId('quota-draft');
    expect(await violationsIn(container)).toEqual([]);
  });
});
