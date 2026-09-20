import type { ReactNode } from 'react';

import { TypedError } from './TypedError';
import type { SurfaceState } from './surfaceState';

/**
 * The seven states from design system section 8. A surface that implements five
 * is not finished.
 *
 * Three of them render data and add something beside it, and four render
 * instead of data. The distinction matters: a partial result still shows its
 * rows, and hiding them would be a different lie from the one being prevented.
 */
export interface StateBoundaryProps {
  readonly state: SurfaceState;
  readonly children: ReactNode;
  /**
   * Set only where the same coverage claim is already made, once, somewhere the
   * reader cannot miss it. Four tiles summarising one partially read estate
   * otherwise repeat an identical sentence four times, and announce it four
   * times to a screen reader, which buries the claim rather than making it.
   * It suppresses the sentence and never the rows: the data still renders, and
   * a surface that sets this while showing coverage nowhere is a bug.
   */
  readonly coverageShownElsewhere?: boolean;
}

export function StateBoundary({
  state,
  children,
  coverageShownElsewhere = false,
}: StateBoundaryProps) {
  switch (state.kind) {
    case 'loading':
      return (
        <div data-testid="state" data-state="loading" aria-busy="true">
          {Array.from({ length: state.rows }, (_, index) => (
            <div key={index} data-testid="skeleton-row" style={{ height: '1.5rem' }} />
          ))}
        </div>
      );
    case 'empty':
      return (
        <div data-testid="state" data-state="empty">
          <p>Nothing matches this filter.</p>
          <p>Filter: {state.filter}</p>
        </div>
      );
    case 'never-collected':
      return (
        <div data-testid="state" data-state="never-collected">
          <p>Not yet collected by {state.collector}.</p>
          {state.nextRun ? <p>Next run {state.nextRun}.</p> : null}
        </div>
      );
    case 'failed':
      return (
        <div data-testid="state" data-state="failed">
          <TypedError cause={state.cause} remediation={state.remediation} />
        </div>
      );
    case 'partial':
      return (
        <div data-testid="state" data-state="partial">
          {coverageShownElsewhere ? null : (
            <p role="status">
              {state.missing} missing. {state.reason}
            </p>
          )}
          {children}
        </div>
      );
    case 'stale':
      return (
        <div data-testid="state" data-state="stale" className="meter-stale">
          <p role="status">Data is {state.age} old.</p>
          {children}
        </div>
      );
    case 'degraded':
      return (
        <div data-testid="state" data-state="degraded">
          <p role="status">Failing: {state.failing.join(', ')}.</p>
          {children}
        </div>
      );
    case 'ready':
      return (
        <div data-testid="state" data-state="ready">
          {children}
        </div>
      );
  }
}
