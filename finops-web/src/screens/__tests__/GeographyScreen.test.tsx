import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { GeographyScreen } from '../GeographyScreen';
import { Harness } from './Harness';
import { clientReturning } from './fixtures';
import { geographyFixture, resourceListFixture } from '../../api/fixtures/topology';
import { violationsIn } from '../../components/__tests__/axe';

/**
 * FEAT-061. The cases that carry this file are the three leftovers and the deliberate absence of
 * a default continent.
 *
 * A map is the easiest screen in a product to make dishonest, because omitting something looks
 * like tidiness. Resources with no region, resources in a region whose name we cannot read, and
 * resources in a region nobody could read are three different facts with three different
 * remedies, and a screen that shows only the continents is reporting a smaller estate than exists
 * while looking complete.
 */

const GEOGRAPHY = '/api/v1/inventory/geography';
const EU = '/api/v1/inventory/resources?limit=25&offset=0&geography=eu';
const US = '/api/v1/inventory/resources?limit=25&offset=0&geography=us';

function renderGeography() {
  return render(
    <Harness
      client={clientReturning({
        [GEOGRAPHY]: geographyFixture(),
        [EU]: resourceListFixture(),
        [US]: resourceListFixture(),
      })}
    >
      <GeographyScreen />
    </Harness>,
  );
}

describe('GeographyScreen', () => {
  it('draws the continents from region names and names the regions inside them', async () => {
    renderGeography();
    expect(await screen.findByTestId('world-map')).toBeInTheDocument();
    const choices = screen.getAllByTestId('world-map-choice');
    expect(choices.map((one) => one.getAttribute('data-key'))).toEqual(['us', 'eu']);
    expect(screen.getAllByTestId('world-map-regions')[0]).toHaveTextContent('us-fake-1');
  });

  it('says a marker is a continent and not a datacentre', async () => {
    // The limit of reading geography from a name, stated on the screen rather than in a
    // document nobody opens. A dot that a reader takes for a datacentre is a dot that has
    // misled them about where their data is.
    renderGeography();
    expect(await screen.findByTestId('world-map-caption')).toHaveTextContent(
      /continent and not a datacentre/,
    );
  });

  it('keeps global, unplaceable and refused as three separate answers', async () => {
    // The case this screen exists to get right. Each needs a different remedy: nothing, one more
    // row in the geography table, and a fix to a collection. One combined count would send
    // somebody to fix IAM for not having a region.
    renderGeography();
    expect(await screen.findByTestId('geography-global')).toHaveTextContent(
      /6 resources have no region at all/,
    );
    expect(screen.getByTestId('geography-unplaceable')).toHaveTextContent(
      /2 resources are in 1 region whose name does not say/,
    );
    expect(screen.getByTestId('geography-refused')).toHaveTextContent(
      /every count above is a floor/,
    );
  });

  it('calls a global resource a fact about the service, not a gap', async () => {
    renderGeography();
    expect(await screen.findByTestId('geography-global')).toHaveTextContent(
      /not a gap in the inventory/,
    );
  });

  it('loads nothing until a continent is chosen', async () => {
    // A screen that loads the first continent has decided which continent matters, and on an
    // estate spread across nine of them that decision is wrong eight times out of nine.
    renderGeography();
    expect(await screen.findByTestId('geography-prompt')).toHaveTextContent(
      /Nothing is loaded until you do/,
    );
    expect(screen.queryByTestId('geography-table')).toBeNull();
  });

  it('lists the resources of the continent that was clicked', async () => {
    renderGeography();
    const choices = await screen.findAllByTestId('world-map-choice');
    const europe = choices.find((one) => one.getAttribute('data-key') === 'eu');
    await userEvent.click(europe as HTMLElement);
    expect(await screen.findByTestId('geography-table')).toBeInTheDocument();
    // The heading repeats the count the map claimed, so a disagreement between the two is
    // visible on one screen rather than needing two.
    expect(screen.getByTestId('geography-chosen')).toHaveTextContent('Europe, 12 resources');
    expect(screen.getByTestId('geography-chosen')).toHaveTextContent('eu-fake-1');
  });

  it('closes the list when the same continent is clicked again', async () => {
    // A toggle rather than a one way door. A reader who opened the wrong continent should not
    // have to reload the screen to get back to the map alone.
    renderGeography();
    const choices = await screen.findAllByTestId('world-map-choice');
    const europe = choices.find((one) => one.getAttribute('data-key') === 'eu') as HTMLElement;
    await userEvent.click(europe);
    expect(await screen.findByTestId('geography-table')).toBeInTheDocument();
    await userEvent.click(europe);
    expect(screen.queryByTestId('geography-table')).toBeNull();
    expect(screen.getByTestId('geography-prompt')).toBeInTheDocument();
  });

  it('publishes the denominator on the list, never a bare page', async () => {
    // The same rule as the resource list. A page with no denominator reads as the whole
    // continent, and a reader who acts on that is acting on a subset.
    renderGeography();
    const choices = await screen.findAllByTestId('world-map-choice');
    await userEvent.click(choices[0] as HTMLElement);
    const caption = await screen.findByTestId('geography-table-count');
    expect(caption.textContent).toMatch(/All \d+ of them|The first \d+ of \d+/);
  });

  it('sends a reader to the resource list rather than paging here', async () => {
    // Deliberately not a second pager. The resource list already does paging and filtering, and
    // a second implementation of the offset arithmetic is a second place for it to be wrong.
    renderGeography();
    const choices = await screen.findAllByTestId('world-map-choice');
    await userEvent.click(choices[0] as HTMLElement);
    const table = await screen.findByTestId('geography-resources');
    const more = within(table).queryByTestId('geography-more');
    if (more !== null) {
      expect(more.querySelector('a')).toHaveAttribute(
        'href',
        '/inventory/resources?geography=us',
      );
    }
  });

  it('has no accessibility violations', async () => {
    const { container } = renderGeography();
    await screen.findByTestId('world-map');
    expect(await violationsIn(container)).toEqual([]);
  });
});
