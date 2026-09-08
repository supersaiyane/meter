import { render, screen } from '@testing-library/react';
import { Route, Routes } from 'react-router';
import { describe, expect, it } from 'vitest';

import { QueryFindingDetailScreen } from '../QueryFindingDetailScreen';
import { amountFigure } from '../findingFigure';
import { QUERY_FINDING_DETAILS } from '../../api/fixtures/query';
import { Harness } from './Harness';
import { clientReturning } from './fixtures';
import { queryFindingDetailFixture } from '../../api/fixtures/query';
import { violationsIn } from '../../components/__tests__/axe';

const MODELLED = '11111111-1111-1111-1111-111111111111';
const MEASURED = '22222222-2222-2222-2222-222222222222';

/**
 * The screen reads its id from the route rather than a prop, because the URL is
 * what gets pasted into a ticket.
 */
function renderDetail(id: string) {
  // Live since TASK-P2-021, so the route is stubbed for whichever id the test
  // asks for. An id the estate does not hold answers with a null body, which is
  // what the fixture did and what this screen's not found branch reads.
  const client = clientReturning({
    [`/api/v1/query/findings/${id}`]: queryFindingDetailFixture(id),
  });
  return render(
    <Harness client={client} initialPath={`/governance/queries/${id}`}>
      <Routes>
        <Route path="/governance/queries/:id" element={<QueryFindingDetailScreen />} />
      </Routes>
    </Harness>,
  );
}

describe('QueryFindingDetailScreen', () => {
  it('publishes the formula with its inputs substituted', async () => {
    renderDetail(MODELLED);
    const working = await screen.findByTestId('finding-working');
    // Publishing the arithmetic is what makes a modelled number arguable
    // rather than magic. An engineer must be able to point at the line they
    // disagree with.
    expect(working).toHaveTextContent('8,640 runs per day');
    expect(working).toHaveTextContent('4,096 MiB scanned per run');
    expect(working).toHaveTextContent('30 day window');
    expect(working).toHaveTextContent('$0.005 per GiB scanned');
  });

  it('shows the query as written rather than a summary of it', async () => {
    renderDetail(MODELLED);
    expect(await screen.findByText(/filter @message like \/ERROR\//)).toBeInTheDocument();
  });

  it('says the accuracy is unpublished, exactly once', async () => {
    // Figure already appends the caveat to a modelled figure. A screen that
    // wrote its own would show it twice and read as two separate claims.
    renderDetail(MODELLED);
    await screen.findByTestId('finding-working');
    expect(screen.getAllByText(/accuracy not yet published/i)).toHaveLength(1);
  });

  it('puts no accuracy caveat on a measured finding', async () => {
    // The caveat is provenance driven. An unconditional one would say a
    // measured number is uncertain, which is a different and equally bad lie.
    renderDetail(MEASURED);
    await screen.findByTestId('finding-working');
    expect(screen.queryByText(/accuracy not yet published/i)).toBeNull();
  });

  it('says nothing was found rather than rendering a blank screen', async () => {
    renderDetail('00000000-0000-0000-0000-000000000000');
    expect(await screen.findByTestId('finding-not-found')).toBeInTheDocument();
  });

  it('has no accessibility violations', async () => {
    const { container } = renderDetail(MODELLED);
    await screen.findByTestId('finding-working');
    expect(await violationsIn(container)).toEqual([]);
  });
});

function baseDetail() {
  const detail = QUERY_FINDING_DETAILS[MODELLED];
  if (detail === undefined) {
    throw new Error('the modelled fixture is missing');
  }
  return detail;
}

describe('amountFigure', () => {

  it('omits accuracy entirely when none is published', () => {
    // Absent, not empty. Figure renders "accuracy not yet published" from the
    // absence, and a blank string would render as a published accuracy of
    // nothing.
    const value = amountFigure({ ...baseDetail(), accuracy_percent: null });
    expect(value).toEqual({ kind: 'modelled', amount: 5184 });
  });

  it('passes a published accuracy through to the figure', () => {
    const value = amountFigure({ ...baseDetail(), accuracy_percent: 9 });
    expect(value).toEqual({ kind: 'modelled', amount: 5184, accuracy: '+/- 9%' });
  });

  it('never attaches an accuracy to a measured figure', () => {
    const value = amountFigure({ ...baseDetail(), provenance: 'measured', accuracy_percent: 9 });
    expect(value).toEqual({ kind: 'measured', amount: 5184 });
  });
});
