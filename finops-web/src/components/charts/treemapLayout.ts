/**
 * The squarified treemap layout of Bruls, Huizing and van Wijk, 2000. Cells are laid in rows
 * along the shorter side of the space left, and a row grows while adding a cell keeps its
 * worst aspect ratio from getting worse, which keeps cells as square as the values allow and
 * so keeps their areas comparable by eye.
 */

export interface Box {
  readonly x: number;
  readonly y: number;
  readonly width: number;
  readonly height: number;
}

export interface Placed<T> extends Box {
  readonly item: T;
}

interface Cell<T> {
  readonly item: T;
  readonly area: number;
}

function worst<T>(row: readonly Cell<T>[], side: number): number {
  const sum = row.reduce((total, cell) => total + cell.area, 0);
  const largest = Math.max(...row.map((cell) => cell.area));
  const smallest = Math.min(...row.map((cell) => cell.area));
  return Math.max(
    (side * side * largest) / (sum * sum),
    (sum * sum) / (side * side * smallest),
  );
}

/** One row laid along the shorter side of `box`, and the box that remains. */
function lay<T>(row: readonly Cell<T>[], box: Box): { placed: Placed<T>[]; rest: Box } {
  const sum = row.reduce((total, cell) => total + cell.area, 0);
  if (box.width >= box.height) {
    const width = sum / box.height;
    const placed = row.map((cell, index) => ({
      item: cell.item,
      x: box.x,
      y: box.y + row.slice(0, index).reduce((total, one) => total + one.area / width, 0),
      width,
      height: cell.area / width,
    }));
    return { placed, rest: { ...box, x: box.x + width, width: box.width - width } };
  }
  const height = sum / box.width;
  const placed = row.map((cell, index) => ({
    item: cell.item,
    x: box.x + row.slice(0, index).reduce((total, one) => total + one.area / height, 0),
    y: box.y,
    width: cell.area / height,
    height,
  }));
  return { placed, rest: { ...box, y: box.y + height, height: box.height - height } };
}

export function squarify<T extends { readonly value: number }>(
  items: readonly T[],
  box: Box,
): Placed<T>[] {
  const total = items.reduce((sum, item) => sum + Math.max(item.value, 0), 0);
  if (total <= 0) {
    return [];
  }
  const scale = (box.width * box.height) / total;
  const cells = items
    .filter((item) => item.value > 0)
    .map((item) => ({ item, area: item.value * scale }))
    .sort((a, b) => b.area - a.area);

  const state = cells.reduce<{ placed: Placed<T>[]; rest: Box; row: Cell<T>[] }>(
    ({ placed, rest, row }, cell) => {
      const side = Math.min(rest.width, rest.height);
      if (row.length === 0 || worst([...row, cell], side) <= worst(row, side)) {
        return { placed, rest, row: [...row, cell] };
      }
      const laid = lay(row, rest);
      return { placed: [...placed, ...laid.placed], rest: laid.rest, row: [cell] };
    },
    { placed: [], rest: box, row: [] },
  );
  return state.row.length === 0
    ? state.placed
    : [...state.placed, ...lay(state.row, state.rest).placed];
}
