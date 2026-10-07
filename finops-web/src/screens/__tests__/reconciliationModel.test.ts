import { describe, expect, it } from 'vitest';

import { ApiError } from '../../api/client';
import { reconciliationFixture } from '../../api/fixtures/cost';
import { invoiceMatch } from '../overviewKpis';
import {
  answeredInstead,
  money,
  periodWords,
  signed,
  stateWords,
  tolerancePercent,
} from '../reconciliationModel';

/** The words and the tile figure for invoice reconciliation, FEAT-076 and TASK-P10-005. */

describe('reconciliationModel', () => {
  it('says each state as a reader would and leaves an unknown one as it came', () => {
    expect(stateWords('Matched')).toBe('Matches the invoice');
    expect(stateWords('Currency differs')).toBe('Billed in another currency, not converted');
    expect(stateWords('Something new')).toBe('Something new');
  });

  it('writes a figure that was not compared in words, never as zero', () => {
    expect(money(null, 'USD')).toBe('Not compared');
    expect(signed(null, 'USD')).toBe('Not compared');
    expect(money('15111.6978', 'USD')).toBe('$15,111.70');
  });

  it('says which side is higher', () => {
    expect(signed('2.5', 'USD')).toBe('+$2.50');
    expect(signed('-2.5', 'USD')).toBe('-$2.50');
  });

  it('says the modelled tolerance as a percentage', () => {
    expect(tolerancePercent('0.0001')).toBe('0.01 percent');
  });

  it('explains an open period and a failed read differently', () => {
    const data = reconciliationFixture().data;
    expect(periodWords({ ...data, state: 'Period open' })).toContain(
      'No invoice has been issued',
    );
    expect(periodWords({ ...data, state: 'Not readable', cause: 'Throttled' })).toContain(
      'could not be read: Throttled',
    );
  });

  it("takes the route's own words for a 403 and a 404, and nothing else", () => {
    expect(answeredInstead(new ApiError(403, 'needs the whole organization'))).toBe(
      'needs the whole organization',
    );
    expect(answeredInstead(new ApiError(404, 'not read'))).toBe('not read');
    // As the API sends it: the sentence inside the JSON body, never the body itself.
    expect(answeredInstead(new ApiError(403, JSON.stringify({ detail: 'whole payer' })))).toBe(
      'whole payer',
    );
    expect(answeredInstead(new ApiError(500, 'broken'))).toBeNull();
    expect(answeredInstead(new Error('AccessDenied'))).toBeNull();
    expect(answeredInstead(null)).toBeNull();
  });
});

describe('invoiceMatch', () => {
  it('is the matched share of the invoiced amount, a credit memo counted by its size', () => {
    const facts = invoiceMatch(reconciliationFixture().data, null);
    // 41.33 matched of 15111.6978 + 41.33 + 40 invoiced, before tax.
    expect(facts.value).toBeCloseTo(41.33 / (15111.6978 + 41.33 + 40), 10);
    expect(facts.note).toBe('1 of 3 invoices matched');
    expect(facts.formula).toContain('billing period starting 2026-08-01');
  });

  it('shows no figure for a period with nothing to compare, and says why', () => {
    const facts = invoiceMatch(
      { ...reconciliationFixture().data, state: 'Period open', invoices: [] },
      null,
    );
    expect(facts.value).toBeNull();
    expect(facts.unsupported).toContain('No invoice has been issued');
  });

  it("shows the route's reason in place of a figure when it answered in words", () => {
    const facts = invoiceMatch(undefined, 'needs the whole organization');
    expect(facts.value).toBeNull();
    expect(facts.unsupported).toBe('needs the whole organization');
  });

  it('has no figure while nothing has arrived', () => {
    const facts = invoiceMatch(undefined, null);
    expect(facts.value).toBeNull();
    expect(facts.unsupported).toBeUndefined();
  });
});
