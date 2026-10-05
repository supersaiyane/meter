import { readStored, writeStored } from './storage';

/**
 * The theme a person chose, P8 spec section 5.1.
 *
 * The operating system decides until the person does. A choice is pinned on the
 * root element as `data-theme`, which tokens.css reads, and remembered in the
 * person's browser alongside the navigation state. Choosing the system again
 * removes the pin rather than storing a copy of what the system said, so a
 * person whose machine turns dark at night gets dark.
 */

export type ThemeChoice = 'system' | 'light' | 'dark';

export const THEME_KEY = 'meter.theme';

/** What was chosen before, and the system when nothing was or the value is unknown. */
export function storedTheme(): ThemeChoice {
  const value = readStored(THEME_KEY);
  return value === 'light' || value === 'dark' ? value : 'system';
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
