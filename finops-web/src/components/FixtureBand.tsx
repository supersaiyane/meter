import type { SurfaceSource } from '../api/fixtureSeam';

export interface FixtureBandProps {
  readonly source: SurfaceSource;
}

/**
 * The one honest way to show a screen before its data is real.
 *
 * It renders in the trust strip, in the same place the coverage warning goes,
 * because it is the same kind of claim: something about this view is not what a
 * reader would otherwise assume.
 *
 * It is not gated on a build flag or an environment variable. A marker that only
 * appears in development is absent exactly when it matters, and a product whose
 * claim is that you can always tell how much a number is worth trusting cannot
 * ship invented numbers that look real.
 */
export function FixtureBand({ source }: FixtureBandProps) {
  if (source === 'route') {
    return null;
  }
  return (
    <p data-testid="fixture-band" data-state="fixture" role="status">
      FIXTURE DATA. This screen is not connected to a collector yet.
    </p>
  );
}
