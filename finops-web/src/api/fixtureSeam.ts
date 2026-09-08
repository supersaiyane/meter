/**
 * Contract first delivery, per `docs/13-UI-ARCHITECTURE.md` section 11.
 *
 * A screen is built against a typed fixture before its route exists. The set
 * below is the single declaration of which paths are still invented, and
 * `tests/api/test_fixture_surfaces.py` fails the build the moment one of them is
 * registered in the application. That test is what makes the set impossible to
 * forget, which matters because a forgotten entry means a fixture rendering as
 * real data.
 *
 * A route that fails does not fall back to the fixture. It raises, the screen
 * renders the typed cause, and no numeral appears.
 */

export type SurfaceSource = 'route' | 'fixture';

export interface Resolved<T> {
  readonly data: T;
  readonly source: SurfaceSource;
}

/**
 * Route templates whose screens exist and whose routes do not. Emptied as
 * routes land.
 *
 * These are templates, not concrete URLs, written the way FastAPI writes
 * `route.path`. A detail screen fetches `/api/v1/query/findings/abc-123` and
 * declares `/api/v1/query/findings/{id}`, so the guard can compare like with
 * like.
 */
export const FIXTURE_SURFACES: ReadonlySet<string> = new Set([
  // Findings, the finding detail and the instances went live with
  // TASK-P2-021 and came out of this set the moment they did, because
  // tests/api/test_fixture_surfaces.py fails the build otherwise.
  //
  // Enforcement stays. TASK-P2-016 is parked on infrastructure ISS-122 records
  // as never provisioned, so there is nothing behind that route and the screen
  // keeps saying its data is invented.
  '/api/v1/query/enforcement',
]);

export function resolveSurface<T>(
  template: string,
  live: () => Promise<T>,
  fixture: () => T,
): () => Promise<Resolved<T>> {
  return async () => {
    if (FIXTURE_SURFACES.has(template)) {
      return { data: fixture(), source: 'fixture' };
    }
    return { data: await live(), source: 'route' };
  };
}
