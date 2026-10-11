import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

/**
 * Which views a screen can export, and the registry the Export menu reads. FEAT-067.
 *
 * The server decides what an export holds: every list route a screen reads answers
 * `format=xlsx` and `format=csv` through one responder, behind the same guard as the screen,
 * P8 spec section 5.5. All the browser does is ask for the view it is showing, with the query it
 * is showing it under, so the file is the screen's rows and never a copy assembled here.
 *
 * Registration happens in the query hooks rather than in each screen, so a screen cannot read a
 * view and forget to offer it. Only a hook rendered inside a screen registers: the shell provides
 * the registry around the screen alone, so a figure the shell reads for itself never appears in
 * a screen's Export menu.
 */

export type ExportFormat = 'xlsx' | 'csv';

/**
 * Every route the API exports, by the template FastAPI names it, with the title the server
 * gives the file. The routes without one are a graph, one object, or one item's detail, and
 * `tests/api/test_export_routes.py` names each with its reason.
 */
export const EXPORT_TITLES: Readonly<Partial<Record<string, string>>> = {
  '/api/v1/accounts': 'Accounts',
  '/api/v1/catalog/instance-types': 'Instance types',
  '/api/v1/catalog/prices': 'Prices',
  '/api/v1/assistant/exchanges': 'Assistant questions',
  '/api/v1/assistant/digests': 'Assistant digests',
  '/api/v1/assistant/redactions': 'Assistant redactions',
  '/api/v1/cost/containers': 'Container cost',
  '/api/v1/cost/summary': 'Cost summary',
  '/api/v1/cost/by-service': 'Cost by service',
  '/api/v1/cost/by-account': 'Cost by account',
  '/api/v1/cost/allocation': 'Cost by tag',
  '/api/v1/cost/trend': 'Daily cost',
  '/api/v1/cost/anomalies': 'Cost anomalies',
  '/api/v1/cost/budgets': 'Budgets',
  '/api/v1/cost/commitments': 'Commitments',
  '/api/v1/cost/showback': 'Showback',
  '/api/v1/cost/explore': 'Cost Explorer',
  '/api/v1/cost/forecast': 'Spend forecast',
  '/api/v1/cost/reconciliation': 'Invoice reconciliation',
  '/api/v1/ingest/runs': 'Collector runs',
  '/api/v1/health/freshness': 'Freshness',
  '/api/v1/inventory/resources': 'Resources',
  '/api/v1/inventory/geography': 'Geography',
  '/api/v1/inventory/clusters': 'Clusters',
  '/api/v1/org/tree': 'Organisation',
  '/api/v1/platform/cost': 'Platform cost',
  '/api/v1/query/findings': 'Query cost',
  '/api/v1/query/groups': 'Query cost by cause',
  '/api/v1/query/adhoc': 'Ad hoc queries',
  '/api/v1/query/instances': 'Query surfaces',
  '/api/v1/governance/quotas': 'Quotas',
  '/api/v1/governance/quotas/requests': 'Quota requests',
  '/api/v1/waste/recommendations': 'Recommendations',
  '/api/v1/waste/recommendations/{recommendation_id}/alternatives': 'Alternatives',
  '/api/v1/waste/refusals': 'Refusals',
  '/api/v1/waste/savings': 'Realized savings',
  '/api/v1/savings/ledger': 'Savings ledger',
  '/api/v1/savings/ledger/credits': 'Savings ledger credits',
  '/api/v1/waste/score': 'Waste score',
  '/api/v1/waste/containers': 'Container usage',
};

/** One view a screen is showing, and the path it was read with, query included. */
export interface ExportView {
  readonly title: string;
  readonly path: string;
}

/** Offer a view, and get back the call that withdraws it. */
export type RegisterExport = (view: ExportView) => () => void;

export const ExportContext = createContext<RegisterExport | undefined>(undefined);

/** The path a file is asked for with: the view's own, query and all, plus the format. */
export function withFormat(path: string, format: ExportFormat): string {
  const at = path.indexOf('?');
  const params = new URLSearchParams(at === -1 ? '' : path.slice(at + 1));
  params.set('format', format);
  return `${at === -1 ? path : path.slice(0, at)}?${params.toString()}`;
}

/**
 * Offer this view in the screen's Export menu for as long as it is on screen. A route the API
 * does not export, a path not yet known, and a hook outside any screen offer nothing.
 *
 * `named` replaces the route's own title where one screen reads a route more than once, as the
 * Overview reads Cost Explorer, because two entries both called Cost Explorer cannot be told
 * apart in the menu.
 */
export function useExportable(template: string, path: string, named?: string): void {
  const register = useContext(ExportContext);
  const exported = EXPORT_TITLES[template];
  const title = exported === undefined ? undefined : (named ?? exported);
  useEffect(() => {
    if (register === undefined || title === undefined || path === '') {
      return undefined;
    }
    return register({ title, path });
  }, [register, title, path]);
}

/** The registry the shell holds: one entry per path, ordered by title. */
export function useExportRegistry(): {
  readonly views: readonly ExportView[];
  readonly register: RegisterExport;
} {
  const [held, setHeld] = useState<readonly ExportView[]>([]);
  const register = useCallback<RegisterExport>((view) => {
    // Its own object, so two panels reading one route each withdraw only their own entry.
    const entry = { ...view };
    setHeld((current) => [...current, entry]);
    return () => {
      setHeld((current) => current.filter((one) => one !== entry));
    };
  }, []);
  const views = useMemo(() => {
    const byPath = new Map(held.map((view) => [view.path, view]));
    return [...byPath.values()].sort((one, other) => one.title.localeCompare(other.title));
  }, [held]);
  return { views, register };
}

/** The navigation state the report library's Export sends a reader with, FEAT-068. */
export const OPEN_EXPORT = { openExport: true } as const;

/** True when the reader arrived from the report library's Export rather than any other way. */
export function asksForExport(state: unknown): boolean {
  return (
    typeof state === 'object' &&
    state !== null &&
    'openExport' in state &&
    state.openExport === true
  );
}
