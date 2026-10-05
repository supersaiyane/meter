import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { App } from './App';
import type { ApiClient } from './api/client';

const NEVER_ANSWERS: ApiClient = {
  get: () => new Promise(() => undefined),
  getFile: () => new Promise<never>(() => undefined),
  post: () => new Promise(() => undefined),
};

function open(path: string) {
  window.history.pushState({}, '', path);
  return render(<App client={NEVER_ANSWERS} />);
}

function withStorage(stub: Pick<Storage, 'getItem' | 'setItem'>, run: () => void): void {
  const original = Object.getOwnPropertyDescriptor(window, 'localStorage');
  Object.defineProperty(window, 'localStorage', { value: stub, configurable: true });
  try {
    run();
  } finally {
    if (original) {
      Object.defineProperty(window, 'localStorage', original);
    }
  }
}

describe('App', () => {
  beforeEach(() => {
    window.history.pushState({}, '', '/');
  });

  it('renders the shell', () => {
    open('/');
    expect(screen.getByTestId('brand')).toHaveTextContent('Meter');
  });

  it('gives every screen a first level heading naming that screen', () => {
    // The only h1 used to be the product name, so six of the ten screens had no
    // heading at all and a reader navigating by heading landed on nothing. The
    // name comes from the navigation list, so the two cannot disagree.
    for (const [path, name] of [
      ['/', 'Overview'],
      ['/govern/query-cost', 'Query Cost'],
      ['/platform/freshness', 'Data Freshness'],
      ['/inventory/accounts', 'Accounts'],
    ] as const) {
      const { unmount } = open(path);
      expect(screen.getByRole('heading', { level: 1, name })).toBeInTheDocument();
      unmount();
    }
  });

  it('names the screen in the document title, not just the product', () => {
    // Four Meter tabs that all read "Meter" cannot be told apart.
    open('/govern/query-cost');
    expect(document.title).toBe('Query Cost, Meter');
  });

  it('does not tell a screen named after the product about the product twice', () => {
    open('/platform/cost');
    expect(document.title).toBe('Meter Cost');
  });

  it('titles a detail page with the screen it was reached from', () => {
    // A finding detail is not in the navigation, and the screen names the
    // finding itself underneath.
    open('/govern/query-cost/findings/abc-123');
    expect(screen.getByRole('heading', { level: 1, name: 'Query Cost' })).toBeInTheDocument();
  });

  it('opens only the group holding the current screen', () => {
    // One group open at a time, by the owner's ask later on 2026-10-05. Nine groups fully
    // expanded is a wall of links; one open group is a menu pointing at where the reader is.
    open('/govern/query-cost');
    expect(screen.getByTestId('group-Govern')).toHaveAttribute('open');
    for (const label of [
      'Analyze',
      'Plan',
      'Optimize',
      'Inventory',
      'Report',
      'Assist',
      'Platform',
    ]) {
      expect(screen.getByTestId(`group-${label}`)).not.toHaveAttribute('open');
    }
  });

  it('opens one group at a time: opening another closes the one that was open', () => {
    open('/govern/query-cost');
    const plan = screen.getByTestId<HTMLDetailsElement>('group-Plan');
    plan.open = true;
    fireEvent(plan, new Event('toggle'));
    expect(screen.getByTestId('group-Plan')).toHaveAttribute('open');
    expect(screen.getByTestId('group-Govern')).not.toHaveAttribute('open');
  });

  it('closes the open group when the reader closes it, and leaves every group closed', () => {
    open('/govern/query-cost');
    const govern = screen.getByTestId<HTMLDetailsElement>('group-Govern');
    govern.open = false;
    fireEvent(govern, new Event('toggle'));
    expect(document.querySelectorAll("nav[aria-label='Sections'] details[open]")).toHaveLength(
      0,
    );
  });

  it('on a narrow screen opens the menu as a drawer, and Escape closes it', () => {
    // At or below 1024 pixels the rail is a bar across the top and its menu a drawer, closed
    // until asked for, so a phone never opens on a wall of links.
    const original = Object.getOwnPropertyDescriptor(window, 'matchMedia');
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: (query: string) => ({
        matches: true,
        media: query,
        addEventListener: () => undefined,
        removeEventListener: () => undefined,
      }),
    });
    try {
      open('/govern/query-cost');
      expect(screen.getByTestId('shell')).toHaveAttribute('data-layout', 'narrow');
      expect(screen.queryByRole('navigation', { name: 'Sections' })).toBeNull();
      fireEvent.click(screen.getByTestId('nav-toggle'));
      expect(screen.getByRole('navigation', { name: 'Sections' })).toBeInTheDocument();
      fireEvent.keyDown(window, { key: 'Escape' });
      expect(screen.queryByRole('navigation', { name: 'Sections' })).toBeNull();
    } finally {
      if (original === undefined) {
        Reflect.deleteProperty(window, 'matchMedia');
      } else {
        Object.defineProperty(window, 'matchMedia', original);
      }
    }
  });

  it('opens the group a detail page was reached from', () => {
    open('/govern/query-cost/findings/abc-123');
    expect(screen.getByTestId('group-Govern')).toHaveAttribute('open');
  });

  it('draws Overview as a link rather than a section holding only itself', () => {
    open('/');
    expect(screen.getByTestId('nav-self-link')).toHaveTextContent('Overview');
    expect(screen.queryByTestId('group-Overview')).toBeNull();
  });

  it('keeps every screen in the document, open section or not', () => {
    // In the document, which is not the same as reachable. A real browser takes
    // a closed details element out of the accessibility tree, so these links
    // are one expansion away rather than tabbable where they stand, and jsdom
    // does not model that. What this holds is that a closed section never
    // removes a screen from the page: the unbuilt ones are listed on purpose,
    // and dropping them would hide the roadmap. The journey asserts the
    // browser's own behaviour, which is the part this cannot see.
    open('/');
    for (const href of [
      '/analyze/explorer',
      '/optimize',
      '/inventory/accounts',
      '/govern/query-cost',
    ]) {
      expect(
        document.querySelector(`nav[aria-label='Sections'] a[href='${href}']`),
      ).not.toBeNull();
    }
  });

  it('collapses the navigation, and takes it out of the tab order with it', () => {
    open('/');
    const toggle = screen.getByTestId('nav-toggle');
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('navigation', { name: 'Sections' })).toBeInTheDocument();

    fireEvent.click(toggle);

    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    // Hidden rather than painted over, so a keyboard user does not tab through
    // links they cannot see.
    expect(screen.queryByRole('navigation', { name: 'Sections' })).toBeNull();
    expect(screen.getByTestId('shell')).toHaveAttribute('data-nav', 'collapsed');
  });

  it('remembers the navigation state between visits', () => {
    // This environment supplies a localStorage with no methods on it, so a real
    // store has to be installed to exercise the path at all. Without one the
    // component takes its catch branch and the persistence is never tested.
    const store = new Map<string, string>();
    withStorage(
      {
        getItem: (key: string) => store.get(key) ?? null,
        setItem: (key: string, value: string) => {
          store.set(key, value);
        },
      },
      () => {
        open('/');
        fireEvent.click(screen.getByTestId('nav-toggle'));
        expect(store.get('meter.nav')).toBe('collapsed');

        cleanup();
        open('/');
        expect(screen.getByTestId('shell')).toHaveAttribute('data-nav', 'collapsed');
      },
    );
  });

  it('opens the navigation anyway when storage refuses to answer', () => {
    // Private windows and blocked site data throw on access rather than
    // returning null. A preference that cannot be read is not a reason to
    // render a shell with no menu in it.
    withStorage(
      {
        getItem: () => {
          throw new Error('site data is blocked');
        },
        setItem: () => {
          throw new Error('site data is blocked');
        },
      },
      () => {
        open('/');
        expect(screen.getByTestId('shell')).toHaveAttribute('data-nav', 'expanded');
        expect(screen.getByRole('navigation', { name: 'Sections' })).toBeInTheDocument();
      },
    );
  });

  it('lands on Overview, which promises nothing that has already shipped', () => {
    // The front page named the sub project behind each unfilled slot, and the last one,
    // realized savings, still said P3 after P3 shipped. Nothing is left to arrive there,
    // so it draws no rail. Read inside the screen rather than the whole page, because the
    // navigation still lists screens as arriving, which is true.
    open('/');
    expect(screen.queryByTestId('not-built')).toBeNull();
    expect(screen.queryByTestId('home-rail')).toBeNull();
    const page = screen.getByRole('main');
    expect(page).not.toHaveTextContent(/arrives with/i);
    expect(page).not.toHaveTextContent(/\bP3\b/);
  });

  it('tells a wrong address apart from a screen that is merely unbuilt', () => {
    // Two different conditions. A reader who cannot tell them apart cannot tell
    // a roadmap entry from a typo.
    open('/nonsense');
    expect(screen.getByTestId('not-a-screen')).toHaveTextContent('/nonsense');
    expect(screen.queryByTestId('not-built')).toBeNull();
  });

  it('marks the current screen for assistive technology', () => {
    // Read inside the Sections menu, because the screen's first tab carries the
    // same name and marks itself too.
    open('/inventory/accounts');
    const sections = screen.getByRole('navigation', { name: 'Sections' });
    expect(sections.querySelector("a[href='/inventory/accounts']")).toHaveAttribute(
      'aria-current',
      'page',
    );
  });

  it('opens a built screen at its own route', () => {
    open('/platform/ingest');
    expect(screen.queryByTestId('not-built')).toBeNull();
  });

  it('sends a path that moved in P8 to its new home, and keeps the query', () => {
    // A bookmark, a digest link or a link in a pull request body made before
    // 2026-10-05 still lands. sections.test.ts enumerates every such path.
    open('/waste?finding=abc');
    expect(window.location.pathname).toBe('/optimize');
    expect(window.location.search).toBe('?finding=abc');
    expect(
      screen.getByRole('heading', { level: 1, name: 'Recommendations' }),
    ).toBeInTheDocument();
  });

  it('sends an old finding detail to the same finding under Query Cost', () => {
    open('/governance/queries/abc-123');
    expect(window.location.pathname).toBe('/govern/query-cost/findings/abc-123');
    expect(screen.getByRole('heading', { level: 1, name: 'Query Cost' })).toBeInTheDocument();
  });

  it('draws a merged screen as a tab of the screen it joined', () => {
    open('/inventory/accounts/organization');
    const views = screen.getByRole('navigation', { name: 'Accounts views' });
    expect(views.querySelector("a[href='/inventory/accounts/organization']")).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(screen.getByRole('heading', { level: 1, name: 'Accounts' })).toBeInTheDocument();
  });
});
