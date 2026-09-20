import type { SurfaceSource } from '../api/fixtureSeam';

export interface FixtureBandProps {
  /**
   * Undefined while the request is in flight or after it failed. Neither is
   * fixture data, and neither is a route's answer, so neither gets a claim.
   */
  readonly source: SurfaceSource | undefined;
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
  if (source !== 'fixture') {
    // Including the unknown case. A failed request used to default to
    // `fixture`, so a screen that could not reach its route announced that its
    // data was invented, which is a false claim about provenance in a product
    // whose whole argument is that its provenance labels can be trusted.
    return null;
  }
  return (
    <p data-testid="fixture-band" data-state="fixture" role="status">
      FIXTURE DATA. This screen is not connected to a collector yet.
    </p>
  );
}
