import type { ReactNode } from 'react';
import { NavLink } from 'react-router';

import { CoverageBanner } from '../components/CoverageBanner';
import { FreshnessIndicator } from '../components/FreshnessIndicator';
import { TypedError } from '../components/TypedError';
import type { Cause } from '../components/provenance';
import { useAggregateMeta } from './metaRegistry';
import { GROUPS } from './sections';

/**
 * The shell. Coverage and freshness live here rather than on each screen,
 * because they are properties of what the user is looking at rather than of one
 * panel, and a per panel treatment lets a reader carry an impression from one
 * panel to the next without noticing it stopped applying.
 *
 * The coverage banner is not dismissible and has no close control. A banner
 * gets dismissed and the condition does not go away with it.
 *
 * The navigation is seven fixed groups, per ADR-0020. Which screen is current is
 * the router's business, not this component's, which is why there is no section
 * prop: two places deciding what is selected is two places to disagree.
 */

export interface AppShellProps {
  readonly children: ReactNode;
  readonly now?: Date;
}

const KNOWN_CAUSES = new Set<string>([
  'AccessDenied',
  'Throttled',
  'NotOptedIn',
  'Unreachable',
  'SchemaDrift',
]);

export function AppShell({ children, now }: AppShellProps) {
  const meta = useAggregateMeta();

  return (
    <div data-testid="shell" data-degraded={meta.degraded ? 'true' : 'false'}>
      <header>
        <h1>Meter</h1>
        <nav aria-label="Sections">
          {GROUPS.map((group) => (
            <div key={group.label} data-testid={`group-${group.label}`}>
              <h2>{group.label}</h2>
              <ul>
                {group.screens.map((screen) => (
                  <li key={screen.path}>
                    {/* An unbuilt screen is listed and reachable, never hidden.
                        Hiding it would make the product look smaller than it is
                        and would hide the roadmap. */}
                    <NavLink
                      to={screen.path}
                      end
                      {...(screen.arrives ? { 'data-arrives': screen.arrives } : {})}
                    >
                      {screen.label}
                      {screen.arrives ? (
                        <span className="meter-arrives"> arrives with {screen.arrives}</span>
                      ) : null}
                    </NavLink>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>

        <CoverageBanner visible={meta.visible} total={meta.total} />

        {meta.asOf === null || meta.collectedAt === null ? (
          // Never collected is not an empty success and must not read as one.
          <p data-testid="global-freshness" data-state="never-collected">
            Not yet collected
          </p>
        ) : (
          <p data-testid="global-freshness" data-state="collected">
            Oldest in view:
            <FreshnessIndicator
              freshness={{
                asOf: new Date(meta.asOf),
                collectedAt: new Date(meta.collectedAt),
              }}
              {...(now ? { now } : {})}
            />
          </p>
        )}

        {meta.degraded && meta.failures.length > 0 ? (
          // Which collector is failing, rather than a generic error toast.
          <section data-testid="shell-failures" aria-label="Problems affecting this view">
            <ul>
              {meta.failures.map((failure) => (
                <li key={`${failure.scope_key}|${failure.collector}|${failure.cause}`}>
                  {KNOWN_CAUSES.has(failure.cause) ? (
                    <TypedError
                      cause={failure.cause as Exclude<Cause, 'NoData'>}
                      remediation={`${failure.collector} on ${failure.scope_key}. ${failure.remediation}`}
                    />
                  ) : (
                    // A cause the frontend does not know is still shown. Hiding
                    // it because the vocabulary drifted would hide the drift.
                    <span className="meter-failure">
                      {failure.cause} on {failure.scope_key}. {failure.remediation}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </section>
        ) : null}
      </header>

      <main>{children}</main>
    </div>
  );
}
