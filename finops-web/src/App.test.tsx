import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { App } from './App';
import type { ApiClient } from './api/client';

const NEVER_ANSWERS: ApiClient = {
  get: () => new Promise(() => undefined),
};

describe('App', () => {
  it('renders the shell with the accounts section first', () => {
    render(<App client={NEVER_ANSWERS} />);
    expect(screen.getByRole('heading', { name: 'Meter' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Accounts' })).toHaveAttribute(
      'aria-current',
      'page',
    );
  });
});
