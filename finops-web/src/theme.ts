import { readStored, writeStored } from './storage';

/**
 * The theme a person chose, P8 spec sections 2 and 5.1.
 *
 * Light, Frosted Ledger, until the person chooses otherwise, by the owner's decision
 * later on 2026-10-05; before it the operating system decided. A choice is pinned on
 * the root element as `data-theme`, which tokens.css reads, and remembered in the
 * person's browser alongside the navigation state. Choosing the system removes the pin
 * rather than storing a copy of what the system said, so a person whose machine turns
 * dark at night gets dark.
 */

export type ThemeChoice = 'system' | 'light' | 'dark';

export const THEME_KEY = 'meter.theme';

/** The theme for a person who has chosen nothing, or whose stored value is unknown. */
export const DEFAULT_THEME: ThemeChoice = 'light';

/** What was chosen before, and the default when nothing was. */
export function storedTheme(): ThemeChoice {
  const value = readStored(THEME_KEY);
  return value === 'light' || value === 'dark' || value === 'system' ? value : DEFAULT_THEME;
}

export function applyTheme(
  choice: ThemeChoice,
  root: HTMLElement = document.documentElement,
): void {
  if (choice === 'system') {
    delete root.dataset.theme;
  } else {
    root.dataset.theme = choice;
  }
}

export function chooseTheme(choice: ThemeChoice): void {
  writeStored(THEME_KEY, choice);
  applyTheme(choice);
}
