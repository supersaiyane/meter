/**
 * The component layer, built once in P0 and used by every sub project.
 *
 * Note what is not here: there is no exported way to render a bare number. A
 * figure reaches a user through `Figure`, which requires its provenance and its
 * freshness, or it does not reach them at all. The moment a raw formatter is
 * exported, a screen will use it under time pressure and the guarantee that
 * every number on every page carries its provenance is gone.
 */

export { CoverageBanner, type CoverageBannerProps } from './CoverageBanner';
export { DataTable, type DataTableProps } from './DataTable';
export { Figure, type FigureProps } from './Figure';
export { FixtureBand, type FixtureBandProps } from './FixtureBand';
export { FreshnessIndicator, type FreshnessIndicatorProps } from './FreshnessIndicator';
export { SeverityBadge, type Severity, type SeverityBadgeProps } from './SeverityBadge';
export { Sparkline, type SparklineProps } from './Sparkline';
export { StateBoundary, type StateBoundaryProps } from './StateBoundary';
export { TypedError, type TypedErrorProps } from './TypedError';
export {
  CAUSE_LABEL,
  formatAge,
  isStale,
  rendersAsNumeral,
  type Cause,
  type FigureValue,
  type Freshness,
  type Provenance,
} from './provenance';
export { SURFACE_STATES, type SurfaceState, type SurfaceStateKind } from './surfaceState';
export { ROW_HEIGHT, VIRTUALISE_ABOVE, type Column } from './tableConfig';
