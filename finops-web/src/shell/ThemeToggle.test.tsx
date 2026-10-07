import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { THEME_KEY } from '../theme';
import { ThemeToggle } from './ThemeToggle';

// This environment supplies a localStorage with no methods on it, so a working
// store is installed for each case, as App.test.tsx and storage.test.ts do.
const original = Object.getOwnPropertyDescriptor(window, 'localStorage');
const store = new Map<string, string>();

beforeEach(() => {
  store.clear();
  Object.defineProperty(window, 'localStorage', {
    value: {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => {
        store.set(key, value);
      },
    },
    configurable: true,
  });
  delete document.documentElement.dataset.theme;
});

afterEach(() => {
  if (original) {
    Object.defineProperty(window, 'localStorage', original);
  }
});

describe('ThemeToggle', () => {
  it('offers the system, light and dark, and starts on light', () => {
    // Light for a reader who has chosen nothing, P8 spec section 2.
    render(<ThemeToggle />);
    expect(screen.getByRole('group', { name: 'Theme' })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Light' })).toBeChecked();
    expect(screen.getByRole('radio', { name: 'System' })).not.toBeChecked();
    expect(screen.getByRole('radio', { name: 'Dark' })).not.toBeChecked();
  });

  it('applies and remembers what a person picks', async () => {
    const user = userEvent.setup();
    render(<ThemeToggle />);
    await user.click(screen.getByRole('radio', { name: 'Dark' }));
    expect(screen.getByRole('radio', { name: 'Dark' })).toBeChecked();
    expect(document.documentElement.dataset.theme).toBe('dark');
    expect(store.get(THEME_KEY)).toBe('dark');
  });

  it('opens on the choice a person made before', () => {
    store.set(THEME_KEY, 'system');
    render(<ThemeToggle />);
    expect(screen.getByRole('radio', { name: 'System' })).toBeChecked();
  });
});
