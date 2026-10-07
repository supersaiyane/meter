import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { QuotasScreen } from '../QuotasScreen';
import { Harness } from './Harness';
import { clientReturning } from './fixtures';
import { sortEveryColumn } from './sortEveryColumn';
import { quotaRequestsFixture, quotasFixture } from '../../api/fixtures/quotas';
import type { ApiEnvelope, ApiQuota, ApiQuotas } from '../../api/types';
import { violationsIn } from '../../components/__tests__/axe';

/**
 * FEAT-033. Two lists, and the cases that carry this file are all about the second one.
 *
 * The failure being guarded is the one every dashboard makes with this data: a quota nobody
 * measured rendered beside the measured ones, at zero, so a reader concludes their estate has
 * headroom everywhere. Three separate assertions attack it, because it can arrive three ways:
 * the row in the wrong list, a zero in the usage column, and a ratio nobody states so the
 * reader counts the visible rows and believes that is all of them.
 */

const PATH = '/api/v1/governance/quotas';
const REQUESTS_PATH = '/api/v1/governance/quotas/requests';

function renderQuotas(fixture: ApiEnvelope<ApiQuotas> = quotasFixture()) {
  return render(
    <Harness
      client={clientReturning({
        [PATH]: fixture,
        [REQUESTS_PATH]: quotaRequestsFixture(),
      })}
    >
      <QuotasScreen />
    </Harness>,
  );
}

/** The fixture's first measured quota, as a quota rather than a possibly absent one. */
function base(): ApiQuota {
  const [first] = quotasFixture().data.measurable;
  if (first === undefined) {
    throw new Error('the quotas fixture has no measured rows, so the cases below are vacuous');
  }
  return first;
}

function withMeasured(quota: ApiQuota): ApiEnvelope<ApiQuotas> {
  const fixture = quotasFixture();
  return {
    ...fixture,
    data: {
      ...fixture.data,
      measurable: [quota],
      unmeasurable: [],
      measured_count: 1,
      found_count: 1,
    },
  };
}

describe('the two lists', () => {
  it('puts measured and unmeasured quotas in separate tables', async () => {
    renderQuotas();
    expect(await screen.findByTestId('quotas-measured')).toBeTruthy();
    expect(screen.getByTestId('quotas-unmeasured')).toBeTruthy();
    expect(screen.getAllByTestId('quota-measured')).toHaveLength(3);
    expect(screen.getAllByTestId('quota-unmeasured')).toHaveLength(4);
  });

  it('never renders a usage figure for an unmeasured quota', async () => {
    // The row has no usage cell at all, so there is nothing to render as a zero. Asserted by
    // the shape rather than by looking for the string "0", because a zero can arrive as "0",
    // "0.0", "0%" or an empty cell and only the shape rules out all four.
    renderQuotas();
    await screen.findByTestId('quotas-unmeasured');
    for (const row of screen.getAllByTestId('quota-unmeasured')) {
      expect(within(row).queryAllByTestId('percent-cell')).toHaveLength(0);
      expect(within(row).queryAllByTestId('quota-source')).toHaveLength(0);
    }
  });

  it('gives every unmeasured quota a reason a reader can act on', async () => {
    renderQuotas();
    await screen.findByTestId('quotas-unmeasured');
    const reasons = screen.getAllByTestId('quota-reason').map((cell) => cell.textContent);
    expect(reasons).toHaveLength(4);
    expect(reasons.every((reason) => reason.trim().length > 0)).toBe(true);
    // More than one distinct reason, because the estate has more than one cause. A single
    // sentence reused on every row would pass a non empty check and tell a reader nothing.
    expect(new Set(reasons).size).toBeGreaterThan(1);
  });

  it('states the ratio rather than leaving it to be counted', async () => {
    // Both lists are truncated by the route, so counting rows understates the denominator.
    renderQuotas();
    expect((await screen.findByTestId('quotas-ratio')).textContent).toContain('3 of 7');
  });

  it('says the gap belongs to the provider rather than to the product', async () => {
    renderQuotas();
    const ratio = await screen.findByTestId('quotas-ratio');
    expect(ratio.textContent).toContain('AWS publishes');
  });
});

describe('the fullness bar', () => {
  it('draws a quota near its limit differently from one that is not', async () => {
    // Spec section 9's requirement that 90 percent is visually distinct from 10 percent. The
    // figure is the content and the track is the drawing, so the figure is what is checked.
    renderQuotas();
    const rows = await screen.findAllByTestId('quota-measured');
    const tightest = rows[0];
    const loosest = rows[rows.length - 1];
    if (tightest === undefined || loosest === undefined) {
      throw new Error('the fixture needs at least two measured quotas for this comparison');
    }
    const tight = within(tightest).getByTestId('percent-figure').textContent;
    const loose = within(loosest).getByTestId('percent-figure').textContent;
    expect(Number.parseFloat(tight)).toBeGreaterThan(90);
    expect(Number.parseFloat(loose)).toBeLessThan(30);
  });

  it('inverts the ramp, because a full quota is the finding rather than the goal', async () => {
    // The first caller of `PercentCell`'s `inverted` flag. Without it a nearly full quota is
    // drawn in the tone the coverage screens use for good news.
    renderQuotas();
    const row = (await screen.findAllByTestId('quota-measured'))[0];
    if (row === undefined) {
      throw new Error('no measured row rendered');
    }
    expect(within(row).getByTestId('percent-track').getAttribute('data-inverted')).toBe('true');
  });

  it('draws no bar where the limit is not published', async () => {
    // The fraction cannot exist without a denominator, and an empty track reads as a
    // measurement that came back zero.
    renderQuotas(withMeasured({ ...base(), limit: null, headroom: null }));
    const absent = await screen.findByTestId('percent-absent');
    expect(screen.queryAllByTestId('percent-cell')).toHaveLength(0);
    expect(absent.textContent).toContain('not published');
  });
});

describe('what each row says about itself', () => {
  it('names what measured the figure', async () => {
    // Two identical figures, one from CloudWatch and one from Trusted Advisor, are not equally
    // trustworthy, and a reader cannot weigh them without being told which is which.
    renderQuotas();
    const sources = (await screen.findAllByTestId('quota-source')).map(
      (cell) => cell.textContent,
    );
    expect(sources).toContain('CloudWatch usage metric');
    expect(sources).toContain('Trusted Advisor');
  });

  it('says all regions for a global quota rather than showing a blank', async () => {
    // A blank invites a reader to assume a missing value, and a placeholder region invites a
    // screen to show one account level limit once per region and add them up.
    renderQuotas();
    const global = (await screen.findAllByTestId('quota-measured')).filter((row) =>
      row.textContent.includes('all regions'),
    );
    expect(global).toHaveLength(1);
  });
});

describe('accessibility', () => {
  it('has no violations', async () => {
    const { container } = renderQuotas();
    await screen.findByTestId('quotas-measured');
    expect(await violationsIn(container)).toEqual([]);
  });
});

describe('the requests beside the lists', () => {
  it('keeps a refused request rather than showing only the open ones', async () => {
    // A list of open requests answers its own question with silence. Somebody waiting on an
    // increase wants to know it was denied three weeks ago more than they want a short list.
    renderQuotas();
    const rows = await screen.findAllByTestId('quota-request-row');
    const statuses = rows.map((row) => row.getAttribute('data-status'));
    expect(statuses).toContain('DENIED');
    expect(statuses).toContain('PENDING');
  });

  it('counts the open ones rather than the total', async () => {
    renderQuotas();
    const heading = await screen.findByTestId('quota-requests-heading');
    expect(heading.textContent).toContain('One increase request still open');
  });

  it('says Meter reads the history and never adds to it', async () => {
    renderQuotas();
    const table = await screen.findByTestId('quota-requests');
    expect(table.textContent).toContain('never adds to it');
  });

  it('tracks a request for a quota that appears in the unmeasured list', async () => {
    // Tracking and measuring are independent, which is the whole of TASK-P5-008. Asserted
    // against the other list on the same screen, so the two cannot drift apart unnoticed.
    renderQuotas();
    await screen.findAllByTestId('quota-request-row');
    const tracked = screen.getAllByTestId('request-quota-link').map((link) => link.textContent);
    const unmeasured = screen.getAllByTestId('quota-unmeasured').map((row) => row.textContent);
    expect(tracked).toContain('Brokers per account');
    expect(unmeasured.some((text) => text.includes('Brokers per account'))).toBe(true);
  });
});

describe('QuotasScreen sorting', () => {
  it('sorts every column it offers, one way and then the other', async () => {
    const { container } = renderQuotas();
    await screen.findAllByTestId('quota-request-row');
    await screen.findByTestId('quotas-measured');
    expect(sortEveryColumn(container)).toBeGreaterThan(0);
  });
});
