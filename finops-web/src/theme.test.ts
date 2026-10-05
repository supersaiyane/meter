import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { THEME_KEY, applyTheme, chooseTheme, storedTheme } from './theme';

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

describe('the theme a person chose', () => {
  it('follows the operating system until a person chooses', () => {
    expect(storedTheme()).toBe('system');
    applyTheme(storedTheme());
    expect(document.documentElement.dataset.theme).toBeUndefined();
  });

  it('pins a choice and remembers it', () => {
    chooseTheme('dark');
    expect(document.documentElement.dataset.theme).toBe('dark');
    expect(store.get(THEME_KEY)).toBe('dark');
    expect(storedTheme()).toBe('dark');
  });

  it('hands the choice back to the operating system', () => {
    chooseTheme('light');
    chooseTheme('system');
    expect(document.documentElement.dataset.theme).toBeUndefined();
    expect(storedTheme()).toBe('system');
  });

  it('treats a stored value it does not know as no choice', () => {
    store.set(THEME_KEY, 'sepia');
    expect(storedTheme()).toBe('system');
  });
});
