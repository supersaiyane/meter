import type { Cause } from './provenance';

/**
 * The seven states every data surface implements. A surface that implements
 * five is not finished, so the list is a value rather than a comment and a test
 * asserts the boundary handles all of them.
 */
export const SURFACE_STATES = [
  'loading',
  'empty',
  'never-collected',
  'partial',
  'stale',
  'degraded',
  'failed',
] as const;

export type SurfaceStateKind = (typeof SURFACE_STATES)[number] | 'ready';

export type SurfaceState =
  /** A skeleton at the true final dimensions. A spinner hides how much is coming. */
  | { readonly kind: 'loading'; readonly rows: number }
  /** Genuinely nothing matched. The filter is shown so it does not look like a failure. */
  | { readonly kind: 'empty'; readonly filter: string }
  /** Never collected is not an empty success, and must not render as one. */
  | { readonly kind: 'never-collected'; readonly collector: string; readonly nextRun?: string }
  /** Some of it is missing, and the count and the reason stay on screen. */
  | { readonly kind: 'partial'; readonly missing: number; readonly reason: string }
  | { readonly kind: 'stale'; readonly age: string }
  /** Which collector is failing, rather than a generic error toast. */
  | { readonly kind: 'degraded'; readonly failing: readonly string[] }
  | {
      readonly kind: 'failed';
      readonly cause: Exclude<Cause, 'NoData'>;
      readonly remediation: string;
    }
  | { readonly kind: 'ready' };
