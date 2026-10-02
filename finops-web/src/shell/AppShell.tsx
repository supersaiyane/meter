import { useEffect, useState, type ReactNode } from 'react';
import { NavLink, useLocation } from 'react-router';

import { CoverageBanner } from '../components/CoverageBanner';
import { FreshnessIndicator } from '../components/FreshnessIndicator';
import { TypedError } from '../components/TypedError';
import type { Cause } from '../components/provenance';
import { useAggregateMeta } from './metaRegistry';
import { readStored, writeStored } from '../storage';
import { GROUPS, screenTitleFor } from './sections';

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
 *
 * The page heading and the document title are taken from the same navigation
 * list, for the same reason. Before this the only h1 was the product name, so
 * six of the ten screens had no heading at all, every browser tab said "Meter",
 * and a reader navigating by heading landed on a page that named nothing.
 */

export interface AppShellProps {
  readonly children: ReactNode;
  readonly now?: Date;
}

/** Which state the navigation was left in, per browser. */
const NAV_KEY = 'meter.nav';

function navWasCollapsed(): boolean {
  // Absent and unreadable are the same answer here: a shell that cannot read a
  // preference still opens with its menu.
  return readStored(NAV_KEY) === 'collapsed';
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
  const { pathname } = useLocation();
  const title = screenTitleFor(pathname);
  const [navOpen, setNavOpen] = useState(() => !navWasCollapsed());

  useEffect(() => {
    writeStored(NAV_KEY, navOpen ? 'expanded' : 'collapsed');
  }, [navOpen]);

  useEffect(() => {
    // Every tab, bookmark and history entry said "Meter", so a reader with four
    // Meter tabs open could not tell them apart. A screen already named after
    // the product does not get told twice: "Meter cost, Meter" reads as a bug.
    document.title = title.startsWith('Meter') ? title : `${title}, Meter`;
  }, [title]);

  return (
    <div
      data-testid="shell"
      data-nav={navOpen ? 'expanded' : 'collapsed'}
      data-degraded={meta.degraded ? 'true' : 'false'}
    >
      <header>
        {/* Collapsing narrows the grid column rather than painting over the
            navigation, and the navigation is hidden rather than merely made
            invisible, so it leaves the accessibility tree and the tab order
            with it. There is no width transition: the motion rule permits a
            120 ms opacity change and nothing else. */}
        <button
          type="button"
          data-testid="nav-toggle"
          aria-expanded={navOpen}
          aria-controls="sections"
          aria-label={navOpen ? 'Hide navigation' : 'Show navigation'}
          onClick={() => {
            setNavOpen((open) => !open);
          }}
        >
          {navOpen ? 'Hide' : 'Menu'}
        </button>
        {/* The product name, not the page heading. It was an h1, which meant the
            only first level heading on every screen named the product and no
            page named itself. */}
        <p data-testid="brand" hidden={!navOpen}>
          Meter
        </p>
        <nav id="sections" aria-label="Sections" hidden={!navOpen}>
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
      </header>

      {/* One band, full width, above everything. Section 8 of
          docs/13-UI-ARCHITECTURE.md asks for exactly this shape, and it sat in
          the sidebar instead, where a 1440 px screen pushed the freshness line
          below the fold and the page lost the one thing that says how much its
          numbers are worth. */}
      <div data-testid="trust-strip">
        <CoverageBanner coverage={meta.coverage} />

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
      </div>

      <main>
        <h1 data-testid="screen-title">{title}</h1>
        {children}
      </main>
    </div>
  );
}
