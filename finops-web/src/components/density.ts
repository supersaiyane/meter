import { createContext, useContext } from 'react';

/**
 * Whether a figure is being rendered inside a dense table.
 *
 * A context rather than a prop, because a prop is something a new screen can
 * forget. `DataTable` sets it once and every `Figure` inside it reads it, so a
 * table added next year is dense without its author knowing this exists.
 *
 * What dense removes is the freshness line and the accuracy clause, and only
 * those. The three way provenance encoding stays: fill, tilde prefix, and the
 * word. Freshness is not lost, it moves to where the design already puts it,
 * the trust strip above the page, worst case across every collector feeding it.
 * Repeating it per cell made a three figure row about 90 px tall and pushed
 * monthly cost, the sort column, off the right edge of a 1440 px screen.
 */
export const DensityContext = createContext(false);

export function useIsDense(): boolean {
  return useContext(DensityContext);
}
