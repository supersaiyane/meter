import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { App } from './App';
import type { ApiClient } from './api/client';

const NEVER_ANSWERS: ApiClient = {
  get: () => new Promise(() => undefined),
  getText: () => new Promise<string>(() => undefined),
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
      ['/', 'Home'],
      ['/governance/queries', 'Query findings'],
      ['/platform/freshness', 'Freshness'],
      ['/inventory/accounts', 'Accounts'],
    ] as const) {
      const { unmount } = open(path);
      expect(screen.getByRole('heading', { level: 1, name })).toBeInTheDocument();
      unmount();
    }
  });

  it('names the screen in the document title, not just the product', () => {
    // Four Meter tabs that all read "Meter" cannot be told apart.
    open('/governance/queries');
    expect(document.title).toBe('Query findings, Meter');
  });

  it('does not tell a screen named after the product about the product twice', () => {
    open('/platform/cost');
    expect(document.title).toBe('Meter cost');
  });

  it('titles a detail page with the screen it was reached from', () => {
    // A finding detail is not in the navigation, and the screen names the
    // finding itself underneath.
    open('/governance/queries/abc-123');
    expect(
      screen.getByRole('heading', { level: 1, name: 'Query findings' }),
    ).toBeInTheDocument();
  });

  it('opens only the section holding the current screen', () => {
    // The point of the accordion. Seven groups fully expanded is a wall of
    // links; one open group is a menu pointing at where the reader is.
    open('/governance/queries');
    const governance = screen.getByTestId('group-Governance');
    expect(governance).toHaveAttribute('open');
    for (const label of ['Cost', 'Waste', 'Inventory', 'Platform']) {
      expect(screen.getByTestId(`group-${label}`)).not.toHaveAttribute('open');
    }
  });

  it('opens the section a detail page was reached from', () => {
    open('/governance/queries/abc-123');
    expect(screen.getByTestId('group-Governance')).toHaveAttribute('open');
  });

  it('draws Home as a link rather than a section holding only itself', () => {
    open('/');
    expect(screen.getByTestId('nav-self-link')).toHaveTextContent('Home');
    expect(screen.queryByTestId('group-Home')).toBeNull();
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
    for (const href of ['/cost', '/waste', '/inventory/accounts', '/governance/queries']) {
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

  it('lands on Home, which promises nothing that has already shipped', () => {
    // Home named the sub project behind each unfilled slot, and the last one, realized
    // savings, still said P3 after P3 shipped. Nothing is left to arrive on Home, so it
    // draws no rail. Read inside the screen rather than the whole page, because the
    // navigation still lists the Flags screen as arriving, which is true.
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
    open('/inventory/accounts');
    expect(screen.getByRole('link', { name: 'Accounts' })).toHaveAttribute(
      'aria-current',
      'page',
    );
  });

  it('opens a built screen at its own route', () => {
    open('/platform/ingest');
    expect(screen.queryByTestId('not-built')).toBeNull();
  });
});
