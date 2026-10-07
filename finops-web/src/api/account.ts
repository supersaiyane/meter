import { parsePath, useSearchParams, type To } from 'react-router';

/**
 * The account a reader chose, FEAT-075, kept in the address so a shared link opens the same
 * account and moving between screens keeps it.
 *
 * The address key is the one Cost Explorer and Resources already read as their account filter,
 * so those filters and the choice are one thing rather than two that can disagree. The API takes
 * it under a name of its own, because `/api/v1/cost/explore` reads `account` as a list of filter
 * values, and the scope dependency reading that name would narrow a request for two accounts to
 * one of them without saying so.
 */
export const ACCOUNT_KEY = 'account';

/** The API's name for the choice, read by the scope dependency on every route. */
export const CHOSEN_ACCOUNT_PARAM = 'chosen_account';

/** The account chosen in the address, or null for all accounts. */
export function useChosenAccount(): string | null {
  const [params] = useSearchParams();
  const value = params.get(ACCOUNT_KEY);
  return value === null || value === '' ? null : value;
}

/**
 * A destination that keeps the chosen account, so moving between screens never drops it. One
 * that names its own account keeps that one, which is how a row naming an account opens it.
 */
export function keepAccount(to: To, account: string | null): To {
  if (account === null) {
    return to;
  }
  const destination = typeof to === 'string' ? parsePath(to) : to;
  const search = new URLSearchParams(destination.search ?? '');
  if (search.has(ACCOUNT_KEY)) {
    return to;
  }
  search.set(ACCOUNT_KEY, account);
  return { ...destination, search: `?${search.toString()}` };
}

/** An API path narrowed to the chosen account, or the path unchanged for all accounts. */
export function withChosenAccount(path: string, account: string | null): string {
  if (account === null) {
    return path;
  }
  const separator = path.includes('?') ? '&' : '?';
  return `${path}${separator}${CHOSEN_ACCOUNT_PARAM}=${encodeURIComponent(account)}`;
}
