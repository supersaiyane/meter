import { useEffect, useState, type ReactNode } from 'react';
import { useLocation, useSearchParams } from 'react-router';

import { ACCOUNT_KEY, useChosenAccount } from '../api/account';
import { ExportContext, asksForExport, useExportRegistry } from '../api/exportViews';
import { useAccountChoices } from '../api/queries';
import { CoverageBanner } from '../components/CoverageBanner';
import { FreshnessIndicator } from '../components/FreshnessIndicator';
import { TypedError } from '../components/TypedError';
import { collectorName } from '../components/displayNames';
import { isFailureCause } from '../components/provenance';
import { readStored, writeStored } from '../storage';
import { ExportMenu } from './ExportMenu';
import { NavLink } from './links';
import { useAggregateMeta } from './metaRegistry';
import {
  GROUPS,
  activeGroupFor,
  filtersFor,
  isSelfGroup,
  screenTitleFor,
  tabsFor,
} from './sections';
import { ScreenTabs } from './ScreenTabs';
import { SaveView } from './SaveView';
import { SearchBox } from './SearchBox';
import { ThemeToggle } from './ThemeToggle';

/**
 * The shell: a glass rail with the navigation, and a column whose top carries the screen's title
 * and scope line, a toolbar of what can be done with the whole screen, and the trust line. P8 spec
 * sections 2 and 5.1, TASK-P8-018, and the drawings in `docs/design/`.
 *
 * Coverage and freshness live here rather than on each screen, because they are properties of
 * what the user is looking at rather than of one panel, and a per panel treatment lets a reader
 * carry an impression from one panel to the next without noticing it stopped applying. Neither
 * is dismissible: a banner that can be dismissed gets dismissed and the condition does not go
 * with it.
 *
 * The navigation is the Framework groups, per ADR-0020, each a disclosure with one open at a
 * time, by the owner's ask later on 2026-10-05: the group holding the current screen opens with
 * it, and opening another closes it. On a wide screen the rail collapses to its mark; on a narrow
 * one it is a bar across the top whose menu drops over the screen as a drawer. Which screen is
 * current is the router's business, not this component's, which is why there is no section prop.
 *
 * The column is keyed by the screen's path, so moving to another screen cross fades it in, by the
 * owner's choice of rich motion later on 2026-10-05. The fade is the stylesheet's, and a reader
 * who asks for reduced motion gets none.
 */

export interface AppShellProps {
  readonly children: ReactNode;
  readonly now?: Date;
}

/** Which state the wide rail was left in, per browser. */
const NAV_KEY = 'meter.nav';

/** Below this width the rail is a bar across the top and its menu a drawer. */
const NARROW = '(max-width: 1024px)';

function navWasCollapsed(): boolean {
  // Absent and unreadable are the same answer here: a shell that cannot read a
  // preference still opens with its menu.
  return readStored(NAV_KEY) === 'collapsed';
}

function matchesNarrow(): boolean {
  return typeof window.matchMedia === 'function' && window.matchMedia(NARROW).matches;
}

/** Whether the window is narrow now, following it as it is resized or turned. */
function useNarrow(): boolean {
  const [narrow, setNarrow] = useState(matchesNarrow);
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') {
      return undefined;
    }
    const query = window.matchMedia(NARROW);
    const follow = (): void => {
      setNarrow(query.matches);
    };
    query.addEventListener('change', follow);
    return () => {
      query.removeEventListener('change', follow);
    };
  }, []);
  return narrow;
}

/** A drawn icon for the menu button, so it reads the same in every browser and both themes. */
function ToggleIcon({ shape }: { readonly shape: 'hide' | 'show' | 'menu' | 'close' }) {
  const paths = {
    hide: 'M11 4 6 9l5 5M16 4l-5 5 5 5',
    show: 'M4 4l5 5-5 5M9 4l5 5-5 5',
    menu: 'M3 5h14M3 10h14M3 15h14',
    close: 'M5 5l10 10M15 5 5 15',
  } as const;
  return (
    <svg viewBox="0 0 20 20" width="16" height="16" aria-hidden="true" focusable="false">
      <path
        d={paths[shape]}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/**
 * The account a screen is narrowed to, named under its title, FEAT-075 and the owner's choice of
 * 2026-10-06. Rendered only once an account is chosen, so the shell asks for the list of accounts
 * only when it has one to name.
 */
function ChosenAccount({ number }: { readonly number: string }) {
  const choices = useAccountChoices();
  const known = choices.data?.data;
  const account = known?.find((one) => one.account_id === number);
  let said = `Account ${number}`;
  if (account !== undefined && account.name !== number) {
    said = `Account ${account.name}, ${number}`;
  } else if (account === undefined && known !== undefined) {
    // The screens below say the same thing as a typed failure; the title says it in words.
    said = `Account ${number}, which this session cannot see`;
  }
  return <p data-testid="chosen-account">{said}</p>;
}

export function AppShell({ children, now }: AppShellProps) {
  const meta = useAggregateMeta();
  const location = useLocation();
  const { pathname } = location;
  const title = screenTitleFor(pathname);
  const tabbed = tabsFor(pathname);
  const [params] = useSearchParams();
  const taken = filtersFor(pathname);
  // The chosen account is honoured by every screen, at the scope dependency, FEAT-075, so it is
  // never one a screen ignores.
  const ignored = [...new Set(params.keys())].filter(
    (key) => !taken.includes(key) && key !== ACCOUNT_KEY,
  );
  const chosenAccount = useChosenAccount();
  const narrow = useNarrow();
  // The views the screen is reading, offered by its query hooks. Provided around the screen
  // alone, below, so what the shell reads for itself is never offered as the screen's.
  const exports = useExportRegistry();

  // The wide rail's state is the reader's and is remembered. The narrow drawer's is not: it
  // opens when asked for and closes with the screen it opened on, so a phone never opens on a
  // wall of links and a choice made on a desk does not follow the reader onto it.
  const [wideOpen, setWideOpen] = useState(() => !navWasCollapsed());
  const [drawer, setDrawer] = useState<{ readonly open: boolean; readonly at: string }>({
    open: false,
    at: pathname,
  });
  const drawerOpen = drawer.open && drawer.at === pathname;
  const navOpen = narrow ? drawerOpen : wideOpen;

  // One group open at a time. The route opens the group holding the current screen; a group the
  // reader opens or closes stays that way until they move to another screen. Derived rather than
  // synchronised, so there is one fact and nothing to correct in an effect.
  const [chosen, setChosen] = useState<{
    readonly label: string | null;
    readonly at: string;
  } | null>(null);
  const openGroup =
    chosen !== null && chosen.at === pathname ? chosen.label : activeGroupFor(pathname);

  useEffect(() => {
    writeStored(NAV_KEY, wideOpen ? 'expanded' : 'collapsed');
  }, [wideOpen]);

  useEffect(() => {
    // Every tab, bookmark and history entry said "Meter", so a reader with four
    // Meter tabs open could not tell them apart. A screen already named after
    // the product does not get told twice: "Meter cost, Meter" reads as a bug.
    document.title = title.startsWith('Meter') ? title : `${title}, Meter`;
  }, [title]);

  useEffect(() => {
    if (!drawerOpen) {
      return undefined;
    }
    // A drawer over the screen closes the way a reader expects one to.
    const close = (event: KeyboardEvent): void => {
      if (event.key === 'Escape') {
        setDrawer({ open: false, at: pathname });
      }
    };
    window.addEventListener('keydown', close);
    return () => {
      window.removeEventListener('keydown', close);
    };
  }, [drawerOpen, pathname]);

  const toggleLabel = narrow
    ? drawerOpen
      ? 'Close the menu'
      : 'Open the menu'
    : wideOpen
      ? 'Hide navigation'
      : 'Show navigation';
  const toggleShape = narrow ? (drawerOpen ? 'close' : 'menu') : wideOpen ? 'hide' : 'show';
  const toggleText = narrow ? (drawerOpen ? 'Close' : 'Menu') : wideOpen ? 'Hide' : null;

  return (
    <div
      data-testid="shell"
      data-nav={navOpen ? 'expanded' : 'collapsed'}
      data-layout={narrow ? 'narrow' : 'wide'}
      data-degraded={meta.degraded ? 'true' : 'false'}
    >
      <header>
        <div data-testid="rail-top">
          <span data-testid="brand-mark" aria-hidden="true" />
          {/* The product name, not the page heading. It was an h1, which meant the
              only first level heading on every screen named the product and no
              page named itself. */}
          <p data-testid="brand" hidden={!navOpen && !narrow}>
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
            aria-label={toggleLabel}
            onClick={() => {
              if (narrow) {
                setDrawer({ open: !drawerOpen, at: pathname });
              } else {
                setWideOpen((open) => !open);
              }
            }}
          >
            <ToggleIcon shape={toggleShape} />
            {toggleText === null ? null : <span>{toggleText}</span>}
          </button>
        </div>
        <nav id="sections" aria-label="Sections" hidden={!navOpen}>
          {GROUPS.map((group) =>
            isSelfGroup(group) ? (
              // Home is its own only screen. A disclosure here would be a group named
              // Overview containing one link named Overview.
              <NavLink key={group.path} to={group.path} end data-testid="nav-self-link">
                {group.label}
              </NavLink>
            ) : (
              <details
                key={group.label}
                data-testid={`group-${group.label}`}
                open={openGroup === group.label}
                onToggle={(event) => {
                  const nowOpen = event.currentTarget.open;
                  if (nowOpen && openGroup !== group.label) {
                    setChosen({ label: group.label, at: pathname });
                  } else if (!nowOpen && openGroup === group.label) {
                    setChosen({ label: null, at: pathname });
                  }
                }}
              >
                {/* summary carries its own expanded state and keyboard handling.
                    Reimplementing that on a div is how a menu ends up unreachable
                    by keyboard. */}
                <summary>{group.label}</summary>
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
              </details>
            ),
          )}
        </nav>
      </header>

      <main key={pathname}>
        <div data-testid="screen-bar">
          <div data-testid="screen-heading">
            <h1 data-testid="screen-title">{title}</h1>
            {chosenAccount === null ? null : <ChosenAccount number={chosenAccount} />}
            {/* The scope line under the title, as drawn: what this screen is counting. */}
            <CoverageBanner coverage={meta.coverage} chosen={chosenAccount !== null} />
          </div>
          <div data-testid="toolbar">
            <SearchBox />
            <SaveView />
            <ExportMenu views={exports.views} openOnArrival={asksForExport(location.state)} />
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
