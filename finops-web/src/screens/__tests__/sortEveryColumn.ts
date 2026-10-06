import { fireEvent } from '@testing-library/react';
import { expect } from 'vitest';

/**
 * Sorts every sortable column of every table under `root` one way and then the other, and
 * checks each time that the header says which way. TASK-P8-013.
 *
 * A column's sort key is a function nothing calls until a reader sorts, so a screen whose
 * tests never sort carries keys no test has run. Returns how many columns it sorted, so a
 * caller can refuse to pass on a screen that drew no sortable table at all.
 */
export function sortEveryColumn(root: HTMLElement): number {
  const buttonAt = (index: number): HTMLButtonElement => {
    // Found again on every turn, because sorting renders the table again.
    const button = root.querySelectorAll<HTMLButtonElement>('button.meter-sort')[index];
    if (button === undefined) {
      throw new Error(`The sort button at ${String(index)} went away when a column sorted`);
    }
    return button;
  };
  const direction = (index: number): string | null =>
    buttonAt(index).closest('th')?.getAttribute('aria-sort') ?? null;

  const count = root.querySelectorAll('button.meter-sort').length;
  for (let index = 0; index < count; index += 1) {
    fireEvent.click(buttonAt(index));
    const first = direction(index);
    expect(['ascending', 'descending']).toContain(first);
    fireEvent.click(buttonAt(index));
    expect(direction(index)).toBe(first === 'ascending' ? 'descending' : 'ascending');
  }
  return count;
}
