import { useState } from 'react';

import { type ThemeChoice, chooseTheme, storedTheme } from '../theme';

const CHOICES: readonly { readonly value: ThemeChoice; readonly label: string }[] = [
  { value: 'system', label: 'System' },
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
];

/**
 * Three radios rather than one button that cycles. A cycling button hides two
 * of its three states, and the only way back to following the system would be
 * through the theme a person was trying to leave.
 */
export function ThemeToggle() {
  const [choice, setChoice] = useState<ThemeChoice>(storedTheme);

  return (
    <fieldset data-testid="theme-toggle">
      <legend>Theme</legend>
      {CHOICES.map((option) => (
        <label key={option.value}>
          <input
            type="radio"
            name="meter-theme"
            value={option.value}
            checked={choice === option.value}
            onChange={() => {
              chooseTheme(option.value);
              setChoice(option.value);
            }}
          />
          {option.label}
        </label>
      ))}
    </fieldset>
  );
}
