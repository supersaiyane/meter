import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it } from 'vitest';

import {
  EXPORT_TITLES,
  ExportContext,
  useExportable,
  useExportRegistry,
  withFormat,
} from '../exportViews';

/** Which views a screen offers, and the registry behind the Export menu. FEAT-067. */

function Registry({ children }: { readonly children: ReactNode }) {
  const { views, register } = useExportRegistry();
  return (
    <>
      <ul data-testid="offered">
        {views.map((view) => (
          <li key={view.path}>{`${view.title} ${view.path}`}</li>
        ))}
      </ul>
      <ExportContext.Provider value={register}>{children}</ExportContext.Provider>
    </>
  );
}

function Reads({ template, path }: { readonly template: string; readonly path: string }) {
  useExportable(template, path);
  return null;
}

function offered(): string[] {
  return Array.from(screen.getByTestId('offered').children, (item) => item.textContent);
}

describe('withFormat', () => {
  it('adds the format to a path with no query', () => {
    expect(withFormat('/api/v1/cost/trend', 'xlsx')).toBe('/api/v1/cost/trend?format=xlsx');
  });

  it('keeps the view query, which is what makes the file the screen', () => {
    expect(withFormat('/api/v1/cost/explore?group_by=region&period=mtd', 'csv')).toBe(
      '/api/v1/cost/explore?group_by=region&period=mtd&format=csv',
    );
  });

  it('replaces a format already in the path rather than sending two', () => {
    expect(withFormat('/api/v1/cost/trend?format=csv', 'xlsx')).toBe(
      '/api/v1/cost/trend?format=xlsx',
    );
  });
});

describe('the export registry', () => {
  it('offers a view a screen reads, under its title, with its query', () => {
    render(
      <Registry>
        <Reads template="/api/v1/cost/explore" path="/api/v1/cost/explore?group_by=account" />
      </Registry>,
    );
    expect(offered()).toEqual(['Cost Explorer /api/v1/cost/explore?group_by=account']);
  });

  it('offers nothing for a route the API does not export, or a path not yet known', () => {
    render(
      <Registry>
        <Reads template="/api/v1/inventory/topology/{node_id}" path="/api/v1/inventory/x" />
        <Reads template="/api/v1/inventory/resources" path="" />
      </Registry>,
    );
    expect(offered()).toEqual([]);
  });

  it('withdraws a view when the screen reading it leaves', () => {
    const { rerender } = render(
      <Registry>
        <Reads template="/api/v1/cost/trend" path="/api/v1/cost/trend" />
      </Registry>,
    );
    expect(offered()).toHaveLength(1);
    rerender(<Registry>{null}</Registry>);
    expect(offered()).toEqual([]);
  });

  it('offers a view two panels read once, and keeps it while either is on screen', () => {
    const { rerender } = render(
      <Registry>
        <Reads template="/api/v1/cost/budgets" path="/api/v1/cost/budgets" />
        <Reads template="/api/v1/cost/budgets" path="/api/v1/cost/budgets" />
      </Registry>,
    );
    expect(offered()).toEqual(['Budgets /api/v1/cost/budgets']);
    rerender(
      <Registry>
        <Reads template="/api/v1/cost/budgets" path="/api/v1/cost/budgets" />
      </Registry>,
    );
    expect(offered()).toEqual(['Budgets /api/v1/cost/budgets']);
  });

  it('orders views by title so a screen of several reads the same way every time', () => {
    render(
      <Registry>
        <Reads template="/api/v1/cost/trend" path="/api/v1/cost/trend" />
        <Reads template="/api/v1/cost/budgets" path="/api/v1/cost/budgets" />
      </Registry>,
    );
    expect(offered()).toEqual([
      'Budgets /api/v1/cost/budgets',
      'Daily cost /api/v1/cost/trend',
    ]);
  });

  it('offers nothing from a hook outside any screen, the shell reading for itself', () => {
    render(<Reads template="/api/v1/accounts" path="/api/v1/accounts" />);
    expect(screen.queryByTestId('offered')).not.toBeInTheDocument();
  });

  it('names every exported route once, and no two the same', () => {
    const titles = Object.values(EXPORT_TITLES);
    expect(Object.keys(EXPORT_TITLES).every((path) => path.startsWith('/api/v1/'))).toBe(true);
    expect(new Set(titles).size).toBe(titles.length);
    expect(titles).toHaveLength(35);
  });
});
