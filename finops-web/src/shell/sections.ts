/** The five P0 screens, named in one place so the nav and the router agree. */
export const SECTIONS = [
  'Accounts',
  'Organization',
  'Ingest',
  'Freshness',
  'Platform',
] as const;
export type Section = (typeof SECTIONS)[number];
