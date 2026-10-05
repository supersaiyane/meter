import { useEffect, useState, type ReactNode } from 'react';
import { NavLink, useLocation } from 'react-router';

import { CoverageBanner } from '../components/CoverageBanner';
import { FreshnessIndicator } from '../components/FreshnessIndicator';
import { TypedError } from '../components/TypedError';
import { isFailureCause } from '../components/provenance';
import { useAggregateMeta } from './metaRegistry';
import { readStored, writeStored } from '../storage';
import { GROUPS, activeGroupFor, isSelfGroup, screenTitleFor, tabsFor } from './sections';
import { ScreenTabs } from './ScreenTabs';
import { ThemeToggle } from './ThemeToggle';

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

export function AppShell({ children, now }: AppShellProps) {
  const meta = useAggregateMeta();
  const { pathname } = useLocation();
  const title = screenTitleFor(pathname);
  const tabbed = tabsFor(pathname);
  const [navOpen, setNavOpen] = useState(() => !navWasCollapsed());

  // Only the section holding the current screen is open, so the menu is short
  // and points at where the reader already is.
  //
  // Derived rather than synchronised. Holding an open set and correcting it in
  // an effect on every navigation sets state during render, which cascades, and
  // it keeps two facts where one will do. What is stored is only what the
  // reader explicitly chose; everything else follows the route, so navigating
  // into a section opens it and leaves a section the reader opened on purpose
  // alone.
  const activeGroup = activeGroupFor(pathname);
  const [choices, setChoices] = useState<ReadonlyMap<string, boolean>>(() => new Map());
  const isGroupOpen = (label: string): boolean => choices.get(label) ?? label === activeGroup;

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
          {GROUPS.map((group) =>
            isSelfGroup(group) ? (
              // Home is its own only screen. An accordion here would be a
              // section named Home containing one link named Home.
              <NavLink key={group.path} to={group.path} end data-testid="nav-self-link">
                {group.label}
              </NavLink>
            ) : (
              <details
                key={group.label}
                data-testid={`group-${group.label}`}
                open={isGroupOpen(group.label)}
                onToggle={(event) => {
                  const nowOpen = event.currentTarget.open;
                  setChoices((made) =>
                    made.get(group.label) === nowOpen
                      ? made
                      : new Map(made).set(group.label, nowOpen),
                  );
                }}
              >
                {/* summary carries its own expanded state and keyboard
                    handling. Reimplementing that on a div is how a menu ends up
                    unreachable by keyboard. */}
                <summary>{group.label}</summary>
                <ul>
                  {group.screens.map((screen) => (
                    <li key={screen.path}>
                      {/* An unbuilt screen is listed and reachable, never
                          hidden. Hiding it would make the product look smaller
                          than it is and would hide the roadmap. */}
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
              </details>
            ),
          )}
        </nav>
        {/* Hidden with the navigation, for the same reason: a collapsed rail is
            too narrow to hold it, and hidden takes it out of the tab order. */}
        <div data-testid="theme-slot" hidden={!navOpen}>
          <ThemeToggle />
        </div>
      </header>

      {/* One band, full width, above everything. Section 8 of
          docs/13-UI-ARCHITECTURE.md asks for exactly this shape, and it sat in
          the sidebar instead, where a 1440 px screen pushed the freshness line
          below the fold and the page lost the one thing that says how much its
          numbers are worth. */}
      <div data-testid="trust-strip">
        <CoverageBanner coverage={meta.coverage} />

        {meta.freshnessPerFigure ? (
          // Every surface on the page carries its freshness with each figure, because its own
          // envelope has none to give: an exchange records Meter's own work, and each citation
          // carries the as_of of the row it was read from. Said of the citations, because that
          // is where the date is drawn. Not yet collected would be false here, and one date
          // made up for the whole page would be worse.
          <p data-testid="global-freshness" data-state="per-figure">
            Each citation carries its own as of date
          </p>
        ) : meta.asOf === null || meta.collectedAt === null ? (
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
          // A count, then the list behind a disclosure. It used to render every failure
          // verbatim, and on a real estate that is fifteen lines above the fold on every
          // screen: the honesty machinery working, and also the first thing a reader sees
          // instead of their own data.
          //
          // Collapsed rather than dropped. The rule this product runs on is that a failure is
          // never hidden and never rendered as a zero, and a count plus one click breaks
          // neither: the number is always visible, the causes are named in the summary, and
          // nothing has to be fetched to open it. A toast would have broken both, because a
          // toast leaves.
          <section data-testid="shell-failures" aria-label="Problems affecting this view">
            <details>
              <summary data-testid="shell-failures-count">
                <span className="meter-failure">
                  {meta.failures.length === 1
                    ? '1 collection is failing'
                    : `${String(meta.failures.length)} collections are failing`}
                </span>{' '}
                <span>
                  {/* The causes, not the instances. Six AccessDenied rows across six accounts
                      are one thing to fix, and naming the cause is what tells a reader whether
                      it is theirs to fix before they open anything. */}
                  {[...new Set(meta.failures.map((failure) => failure.cause))]
                    .sort()
                    .join(', ')}
                </span>
              </summary>
              <ul>
                {meta.failures.map((failure) => (
                  <li key={`${failure.scope_key}|${failure.collector}|${failure.cause}`}>
                    {isFailureCause(failure.cause) ? (
                      <TypedError
                        cause={failure.cause}
                        remediation={`${failure.collector} on ${failure.scope_key}. ${failure.remediation}`}
                      />
                    ) : (
                      // A cause the frontend does not know is still shown. Hiding it because
                      // the vocabulary drifted would hide the drift.
                      <span className="meter-failure">
                        {failure.cause} on {failure.scope_key}. {failure.remediation}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </details>
          </section>
        ) : null}
      </div>

      <main>
        <h1 data-testid="screen-title">{title}</h1>
        {tabbed ? (
          <ScreenTabs label={tabbed.screen.label} tabs={tabbed.tabs} current={tabbed.current} />
        ) : null}
        {children}
      </main>
    </div>
  );
}
