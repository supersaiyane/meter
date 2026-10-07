import { describe, expect, it } from 'vitest';

import { hrefOf, queryOf } from '../savedViews';

/** A saved view's address, both ways, FEAT-068: what Save view keeps is what Open goes back to. */

describe('the query a view keeps', () => {
  it('holds a parameter given once as its value, and one given twice as both values in order', () => {
    expect(queryOf('?group=service&filter=b&filter=a')).toEqual({
      group: 'service',
      filter: ['b', 'a'],
    });
  });

  it('reads a query string with or without its question mark, and nothing as nothing', () => {
    expect(queryOf('status=ACTIVE')).toEqual({ status: 'ACTIVE' });
    expect(queryOf('')).toEqual({});
    expect(queryOf('?')).toEqual({});
  });

  it('keeps an empty value rather than dropping the parameter', () => {
    expect(queryOf('?q=')).toEqual({ q: '' });
  });
});

describe('the address that opens a view', () => {
  it('is the screen alone when the view keeps no query', () => {
    expect(hrefOf({ screen_path: '/plan/budgets', query: {} })).toBe('/plan/budgets');
  });

  it('carries every value of a repeated parameter, encoded', () => {
    expect(
      hrefOf({
        screen_path: '/analyze/explorer',
        query: { group: 'service', tag: ['a b', 'c&d'] },
      }),
    ).toBe('/analyze/explorer?group=service&tag=a+b&tag=c%26d');
  });

  it('opens what was saved, whatever the query held', () => {
    const search = '?group=service&filter=b&filter=a&q=&account=111122223333';
    const href = hrefOf({ screen_path: '/analyze/explorer', query: queryOf(search) });
    expect(queryOf(href.slice(href.indexOf('?')))).toEqual(queryOf(search));
  });
});
