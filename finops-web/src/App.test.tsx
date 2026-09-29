import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { App } from './App';
import type { ApiClient } from './api/client';

const NEVER_ANSWERS: ApiClient = {
  get: () => new Promise(() => undefined),
  post: () => new Promise(() => undefined),
};

function open(path: string) {
  window.history.pushState({}, '', path);
  return render(<App client={NEVER_ANSWERS} />);
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
    expect(screen.getByRole('heading', { level: 1, name: 'Query findings' })).toBeInTheDocument();
  });

  it('lands on Home, which names what each unfilled slot is waiting for', () => {
    open('/');
    expect(screen.queryByTestId('not-built')).toBeNull();
    expect(screen.getByTestId('home-slot-spend')).toHaveTextContent(/P1 Cost Intelligence/);
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
