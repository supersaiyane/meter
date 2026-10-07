import { Link } from './links';
import type { TabDef } from './sections';

export interface ScreenTabsProps {
  readonly label: string;
  readonly tabs: readonly TabDef[];
  readonly current: string;
}

/**
 * The views of one screen, P8 spec section 5.2: a screen that merged into
 * another is a tab of it.
 *
 * Links rather than an ARIA tablist, because each view has its own address, and
 * an address is what a person bookmarks, opens in a new tab and pastes into a
 * ticket. A tablist would promise arrow keys and panels this is not.
 */
export function ScreenTabs({ label, tabs, current }: ScreenTabsProps) {
  return (
    <nav aria-label={`${label} views`} data-testid="screen-tabs">
      <ul>
        {tabs.map((tab) => (
          <li key={tab.path}>
            <Link to={tab.path} aria-current={tab.path === current ? 'page' : undefined}>
              {tab.label}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
