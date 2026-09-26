import type { ApiSliceCoverage } from '../api/types';

/**
 * How a slice that was not read whole is said out loud.
 *
 * In its own module because two screens need the same sentence. The topology map says it
 * above the graph and the entity page says it above the neighbour list, and those are the
 * same claim about the same row: this part of the estate was not read, so anything drawn
 * from it may be missing edges. Two copies would be two answers to that.
 *
 * The React Refresh rule also refuses a file that exports both a component and a value,
 * which is why this is not a helper inside either screen. Same reason `querySeverity.ts`
 * and `actionRisk.ts` exist.
 *
 * **Wording only.** The state and the typed cause are decided in `finops_ingest/coverage.py`
 * and arrive on the row. Nothing here judges anything, so nothing here can disagree with the
 * collector about which slices were read.
 */
export function saidOf(slice: ApiSliceCoverage): string {
  // Null region is the account's global slice, where the IAM roles live. Never a region
  // nobody could read, because an empty string in a sentence reads as a bug.
  const where = slice.region_id ?? 'the global slice';
  const because = slice.cause === null ? '' : ` (${slice.cause})`;
  return `${slice.account_id} in ${where} is ${slice.state}${because}`;
}
