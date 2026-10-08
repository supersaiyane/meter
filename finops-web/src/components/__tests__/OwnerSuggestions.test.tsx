import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { ApiOwnerSuggestion } from '../../api/types';
import { suggestionText } from '../displayNames';
import { OwnerSuggestions } from '../OwnerSuggestions';

function suggestion(
  source: ApiOwnerSuggestion['source'],
  owner: string,
  kind: ApiOwnerSuggestion['kind'],
  detail: string,
): ApiOwnerSuggestion {
  return {
    owner,
    kind,
    source,
    detail,
    as_of: '2026-08-24T06:00:00Z',
    collected_at: '2026-08-24T06:05:00Z',
  };
}

const CATALOGUE = suggestion('CATALOGUE', 'payments', 'TEAM', 'checkout');
const TAG = suggestion('TAG', 'platform', 'TEAM', 'team');

describe('OwnerSuggestions', () => {
  it('says each suggestion with where it came from, and a pipeline as a pipeline', () => {
    expect(suggestionText(CATALOGUE)).toBe("payments, the catalogue's checkout application");
    expect(suggestionText(TAG)).toBe('platform, its team tag');
    expect(suggestionText(suggestion('CREATOR', 'dev.lead@fake.example', 'PERSON', 'e1'))).toBe(
      'dev.lead@fake.example, who created it',
    );
    expect(suggestionText(suggestion('CREATOR', 'deploy-pipeline', 'AUTOMATION', 'e2'))).toBe(
      'deploy-pipeline, the pipeline that created it',
    );
  });

  it('lists them in the order the server ranked them, each dated', () => {
    render(<OwnerSuggestions id="r1" suggestions={[CATALOGUE, TAG]} createdBefore={null} />);
    const items = within(screen.getByTestId('owner-suggestions-r1')).getAllByRole('listitem');
    expect(items.map((item) => item.textContent)).toEqual([
      "payments, the catalogue's checkout application",
      'platform, its team tag',
    ]);
    expect(items[0]).toHaveAttribute('title', 'As of 2026-08-24');
    expect(screen.queryByTestId('created-before-r1')).toBeNull();
  });

  it('says a resource older than the history was created before it began', () => {
    render(<OwnerSuggestions id="r2" suggestions={[]} createdBefore="2026-05-26T06:05:00Z" />);
    expect(screen.getByTestId('created-before-r2')).toHaveTextContent(
      "created before CloudTrail's 90 days, which begin 2026-05-26",
    );
  });

  it('renders nothing where no source names anybody', () => {
    const { container } = render(
      <OwnerSuggestions id="r3" suggestions={[]} createdBefore={null} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
