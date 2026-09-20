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
    expect(screen.getByRole('heading', { name: 'Meter' })).toBeInTheDocument();
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
