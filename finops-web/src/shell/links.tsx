import {
  Link as RouterLink,
  NavLink as RouterNavLink,
  type LinkProps,
  type NavLinkProps,
} from 'react-router';

import { keepAccount, useChosenAccount } from '../api/account';

/**
 * Every link in the application, keeping the account chosen in the address, FEAT-075.
 *
 * ESLint refuses the router's own `Link` and `NavLink` everywhere else, because one link that
 * dropped the account would open a screen showing every account to a reader who believes it
 * shows one.
 */
export function Link({ to, ...props }: LinkProps) {
  const account = useChosenAccount();
  return <RouterLink to={keepAccount(to, account)} {...props} />;
}

export function NavLink({ to, ...props }: NavLinkProps) {
  const account = useChosenAccount();
  return <RouterNavLink to={keepAccount(to, account)} {...props} />;
}
