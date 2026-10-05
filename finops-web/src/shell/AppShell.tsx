import { useEffect, useState, type ReactNode } from 'react';
import { NavLink, useLocation, useSearchParams } from 'react-router';

import { ExportContext, useExportRegistry } from '../api/exportViews';
import { CoverageBanner } from '../components/CoverageBanner';
import { FreshnessIndicator } from '../components/FreshnessIndicator';
import { TypedError } from '../components/TypedError';
import { collectorName } from '../components/displayNames';
import { isFailureCause } from '../components/provenance';
import { readStored, writeStored } from '../storage';
import { ExportMenu } from './ExportMenu';
import { useAggregateMeta } from './metaRegistry';
import { GROUPS, filtersFor, isSelfGroup, screenTitleFor, tabsFor } from './sections';
import { ScreenTabs } from './ScreenTabs';
import { ThemeToggle } from './ThemeToggle';

/**
 * The shell, as drawn: a glass rail listing every group and its screens, and a column whose top
 * carries the screen's title and scope line, a toolbar of what can be done with the whole screen,
 * and the trust line. P8 spec sections 2 and 5.1, TASK-P8-018, and the drawings in
 * `docs/design/`.
 *
 * Coverage and freshness live here rather than on each screen, because they are properties of
 * what the user is looking at rather than of one panel, and a per panel treatment lets a reader
 * carry an impression from one panel to the next without noticing it stopped applying. Neither
 * is dismissible: a banner that can be dismissed gets dismissed and the condition does not go
 * with it.
 *
 * The navigation is seven fixed groups, per ADR-0020, every one listed with its screens as the
 * drawing lists them. Which screen is current is the router's business, not this component's,
 * which is why there is no section prop: two places deciding what is selected is two places to
 * disagree. The page heading and the document title come from the same navigation list, for the
 * same reason.
 *
 * The column is keyed by the screen's path, so moving to another screen cross fades it in, by the
 * owner's choice of rich motion later on 2026-10-05. The fade is the stylesheet's, and a reader
 * who asks for reduced motion gets none.
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

/** The id of a group's label, so the list under it is named by it. */
function groupLabelId(label: string): string {
  return `nav-group-${label.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;
}

export function AppShell({ children, now }: AppShellProps) {
  const meta = useAggregateMeta();
  const { pathname } = useLocation();
  const title = screenTitleFor(pathname);
  const tabbed = tabsFor(pathname);
  const [params] = useSearchParams();
  const taken = filtersFor(pathname);
  const ignored = [...new Set(params.keys())].filter((key) => !taken.includes(key));
  const [navOpen, setNavOpen] = useState(() => !navWasCollapsed());
  // The views the screen is reading, offered by its query hooks. Provided around the screen
  // alone, below, so what the shell reads for itself is never offered as the screen's.
  const exports = useExportRegistry();

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
        <div data-testid="rail-top">
          {/* The product name, not the page heading. It was an h1, which meant the
              only first level heading on every screen named the product and no
              page named itself. */}
          <p data-testid="brand" hidden={!navOpen}>
            Meter
            <span data-testid="brand-line">FinOps for AWS</span>
          </p>
          {/* Collapsing narrows the grid column rather than painting over the
              navigation, and the navigation is hidden rather than merely made
              invisible, so it leaves the accessibility tree and the tab order
              with it. */}
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
        </div>
        <nav id="sections" aria-label="Sections" hidden={!navOpen}>
          {GROUPS.map((group) =>
            isSelfGroup(group) ? (
              // Home is its own only screen. A heading here would be a group named
              // Overview containing one link named Overview.
              <NavLink key={group.path} to={group.path} end data-testid="nav-self-link">
                {group.label}
              </NavLink>
            ) : (
              <div key={group.label} data-testid={`group-${group.label}`}>
                <p id={groupLabelId(group.label)} data-testid="nav-group-label">
                  {group.label}
                </p>
                <ul aria-labelledby={groupLabelId(group.label)}>
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
            ),
          )}
        </nav>
      </header>

      <main key={pathname}>
        <div data-testid="screen-bar">
          <div data-testid="screen-heading">
            <h1 data-testid="screen-title">{title}</h1>
            {/* The scope line under the title, as drawn: what this screen is counting. */}
            <CoverageBanner coverage={meta.coverage} />
          </div>
          <div data-testid="toolbar">
            <ExportMenu views={exports.views} />
            <ThemeToggle />
          </div>
        </div>

        <div data-testid="trust-strip">
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
                          remediation={`${collectorName(failure.collector)} on ${failure.scope_key}. ${failure.remediation}`}
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

        {tabbed ? (
          <ScreenTabs label={tabbed.screen.label} tabs={tabbed.tabs} current={tabbed.current} />
        ) : null}
        {ignored.length > 0 ? (
          // A parameter this screen does not read stays in the address and is never applied,
          // and is said here, so a link that meant to filter does not land on an unfiltered
          // screen in silence. ISS-235 was exactly that.
          <p data-testid="ignored-filters" role="status">
            Not a filter on this screen, so not applied: {ignored.join(', ')}
          </p>
        ) : null}
        <ExportContext.Provider value={exports.register}>{children}</ExportContext.Provider>
      </main>
    </div>
  );
}
