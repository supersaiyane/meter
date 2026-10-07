import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, useLocation, useNavigate } from 'react-router';
import { describe, expect, it } from 'vitest';

import { useFilters } from '../filters';

const KEYS = ['status', 'region'] as const;

/** A screen in miniature: two filters, the address, and the browser's own buttons. */
function Probe() {
  const { values, set, update } = useFilters(KEYS);
  const location = useLocation();
  const navigate = useNavigate();
  return (
    <div>
      <output data-testid="status">{values.status}</output>
      <output data-testid="region">{values.region}</output>
      <output data-testid="search">{location.search}</output>
      <button
        type="button"
        onClick={() => {
          set('status', 'Broken');
        }}
      >
        broken
      </button>
      <button
        type="button"
        onClick={() => {
          set('status', '');
        }}
      >
        clear
      </button>
      <button
        type="button"
        onClick={() => {
          update({ status: 'Broken', region: '' });
        }}
      >
        both
      </button>
      <button
        type="button"
        onClick={() => {
          void navigate(-1);
        }}
      >
        back
      </button>
      <button
        type="button"
        onClick={() => {
          void navigate(1);
        }}
      >
        forward
      </button>
    </div>
  );
}

function open(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Probe />
    </MemoryRouter>,
  );
}

describe('filters live in the query string', () => {
  it('reads each key the screen names, and the empty string for one the address does not set', () => {
    open('/inventory/accounts?status=HEALTHY');
    expect(screen.getByTestId('status')).toHaveTextContent('HEALTHY');
    expect(screen.getByTestId('region')).toHaveTextContent('');
  });

  it('writes a filter into the address, and takes it out when cleared', () => {
    open('/inventory/accounts');
    fireEvent.click(screen.getByRole('button', { name: 'broken' }));
    expect(screen.getByTestId('search')).toHaveTextContent('?status=Broken');
    fireEvent.click(screen.getByRole('button', { name: 'clear' }));
    expect(screen.getByTestId('search')).toBeEmptyDOMElement();
  });

  it('lets back and forward walk through the filters, as they walk through screens', () => {
    open('/inventory/accounts?status=HEALTHY');
    fireEvent.click(screen.getByRole('button', { name: 'broken' }));
    expect(screen.getByTestId('status')).toHaveTextContent('Broken');
    fireEvent.click(screen.getByRole('button', { name: 'back' }));
    expect(screen.getByTestId('status')).toHaveTextContent('HEALTHY');
    fireEvent.click(screen.getByRole('button', { name: 'forward' }));
    expect(screen.getByTestId('status')).toHaveTextContent('Broken');
  });

  it('keeps a parameter it does not own in the address, so the shell can name it', () => {
    open('/inventory/accounts?colour=red');
    fireEvent.click(screen.getByRole('button', { name: 'broken' }));
    expect(screen.getByTestId('search')).toHaveTextContent('colour=red');
    expect(screen.getByTestId('search')).toHaveTextContent('status=Broken');
  });
});

describe('useFilters, several keys at once', () => {
  it('changes them as one history entry, taking out the ones it empties', () => {
    // Cost Explorer clears a custom period's dates as it sets a preset. As three entries, the
    // back button would walk a reader through two views nobody chose.
    open('/accounts?region=eu');
    fireEvent.click(screen.getByText('both'));
    expect(screen.getByTestId('search')).toHaveTextContent('?status=Broken');
    fireEvent.click(screen.getByText('back'));
    expect(screen.getByTestId('search')).toHaveTextContent('?region=eu');
  });
});
