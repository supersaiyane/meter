import { describe, expect, it } from 'vitest';

import { QUERY_FINDINGS, QUERY_FINDING_DETAILS } from '../fixtures/query';

const GIB = 1024 ** 3;
const DAYS_PER_MONTH = 30;

/**
 * The detail screen publishes the arithmetic so a reader can check it. That is
 * worth nothing if the arithmetic does not produce the number printed above it,
 * and an engineer who checks the sum and finds it wrong stops believing the
 * whole product rather than just that row.
 *
 * Caught in a browser on 2026-09-15: the working read 1,036,800 GiB at $0.005,
 * which is $5,184, printed under a headline figure of $12,400.
 */
describe('query fixtures', () => {
  it('publishes a cost each detail row can actually derive', () => {
    for (const detail of Object.values(QUERY_FINDING_DETAILS)) {
      const gibPerMonth =
        (detail.runs_per_day * detail.bytes_scanned_per_run * DAYS_PER_MONTH) / GIB;
      const derived = gibPerMonth * Number(detail.rate_usd_per_gib);
      expect(derived).toBeCloseTo(Number(detail.monthly_cost), 2);
    }
  });

  it('agrees with the list row for the same finding', () => {
    // Two surfaces quoting different costs for one finding is the disagreement
    // the whole provenance system exists to make impossible.
    for (const finding of QUERY_FINDINGS) {
      const detail = QUERY_FINDING_DETAILS[finding.finding_id];
      expect(detail).toBeDefined();
      expect(detail?.monthly_cost).toBe(finding.monthly_cost);
      expect(detail?.runs_per_day).toBe(finding.runs_per_day);
      expect(detail?.bytes_scanned_per_run).toBe(finding.bytes_scanned_per_run);
      expect(detail?.provenance).toBe(finding.provenance);
    }
  });
});
