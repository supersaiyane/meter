import { render, screen, within } from '@testing-library/react';
import { Route, Routes } from 'react-router';
import { describe, expect, it } from 'vitest';

import { blastRadiusFixture, entityFixture } from '../../api/fixtures/topology';
import type { ApiBlastRadius, ApiEntity, ApiEnvelope } from '../../api/types';
import { violationsIn } from '../../components/__tests__/axe';
import { EntityScreen } from '../EntityScreen';
import { Harness } from './Harness';
import { clientReturning } from './fixtures';

/**
 * FEAT-053. The destination every list in the product needed and did not have.
 *
 * The cases that carry this file are the two admissions, not the fields. Rendering an
 * account identifier is not a claim anybody can get wrong. What can go wrong is a page that
 * reads as reassuring: a neighbour list drawn from a slice nobody could read, a cost of zero
 * where the bill simply said nothing, and an empty finding list on a resource whose findings
 * all failed to join.
 */

const NODE = '3f8c1a2b-4d5e-4f60-8a71-9b2c3d4e5f60';
const SUBNET = '4a9d2b3c-5e6f-4071-9b82-0c3d4e5f6071';

function renderEntity(
  body: ApiEnvelope<ApiEntity> | null = entityFixture(NODE),
  nodeId: string = NODE,
  blast?: ApiEnvelope<ApiBlastRadius>,
) {
  // A null body is what the API's 404 resolves to through the client, and it is the shape
  // the not found branch reads. `clientReturning` takes an envelope over unknown, so this
  // needs no cast: a cast here would be asserting something the stub already accepts.
  const answer: ApiEnvelope<unknown> = body ?? { data: null, meta: entityFixture(nodeId).meta };
  const client = clientReturning({
    [`/api/v1/inventory/nodes/${nodeId}`]: answer,
    // FEAT-044's own route. Refused by default, from the fixture, because a refusal is the half
    // of that feature easiest to leave unexercised.
    [`/api/v1/inventory/nodes/${nodeId}/blast-radius`]: blast ?? blastRadiusFixture(),
  });
  return render(
    <Harness client={client} initialPath={`/inventory/resources/${nodeId}`}>
      <Routes>
        <Route path="/inventory/resources/:nodeId" element={<EntityScreen />} />
      </Routes>
    </Harness>,
  );
}

/** The fixture with one field changed, because every case here is about one field. */
function withEntity(changes: Partial<ApiEntity>): ApiEnvelope<ApiEntity> {
  const base = entityFixture(NODE);
  return { ...base, data: { ...base.data, ...changes } };
}

describe('EntityScreen', () => {
  it('says what the resource is and where to find it', async () => {
    renderEntity();
    // The ARN whole, because a truncated identifier is not an identifier and a reader has to
    // be able to paste it into their own console.
    const arn = await screen.findByTestId('entity-arn');
    expect(arn).toHaveTextContent('arn:aws:ec2:fake-region-a:fake-platform-a:vpc/vpc-platform');
    expect(screen.getByTestId('entity-identity')).toHaveTextContent('fake-platform-a');
  });

  it('warns that the neighbour list may be short before showing it', async () => {
    // The first of the two admissions, and the reason the banner is above the list rather
    // than below it. A reader who reads the list first has already concluded it is complete.
    renderEntity();
    const banner = await screen.findByTestId('entity-coverage');
    expect(banner).toHaveTextContent(/may be attached to things that are not listed/);
    expect(banner).toHaveTextContent('fake-platform-a in fake-region-a is PARTIAL (Throttled)');
  });

  it('shows no coverage warning when the slice was read whole', async () => {
    const complete = withEntity({
      coverage: {
        account_id: 'fake-platform-a',
        region_id: 'fake-region-a',
        state: 'COMPLETE',
        cause: null,
        node_count: 27,
        edge_count: 40,
        as_of: '2026-08-24T06:00:00Z',
        collected_at: '2026-08-24T06:05:00Z',
      },
    });
    renderEntity(complete);
    await screen.findByTestId('entity-neighbours');
    expect(screen.queryByTestId('entity-coverage')).toBeNull();
    expect(screen.queryByTestId('entity-coverage-missing')).toBeNull();
  });

  it('reports a missing coverage row rather than assuming the slice was read', async () => {
    // Should be impossible, because the collector writes a row per enrolled slice on every
    // run. Treating a missing row as a healthy one is the exact failure the coverage table
    // exists to prevent, so the screen refuses to make that assumption quietly.
    renderEntity(withEntity({ coverage: null }));
    const banner = await screen.findByTestId('entity-coverage-missing');
    expect(banner).toHaveTextContent(/No coverage was recorded/);
  });

  it('says the bill does not mention the resource rather than showing zero', async () => {
    // Null is not zero. A resource whose charges land under a parent, and one newer than the
    // period, both arrive here, and a zero would tell a reader it is free.
    renderEntity(withEntity({ monthly_cost: null }));
    const absent = await screen.findByTestId('entity-cost-absent');
    expect(absent).toHaveTextContent(/not the same as costing nothing/);
    expect(absent).toHaveTextContent('2026-08-01');
    expect(screen.queryByTestId('entity-cost')).toBeNull();
  });

  it('marks the cost measured and the saving modelled on the same page', async () => {
    // The pair that makes this worth asserting. Both numbers are money, one came off the
    // bill and one came out of a model, and a page that rendered them identically would be
    // inviting a reader to treat an estimate as a fact.
    renderEntity();
    const cost = await screen.findByTestId('entity-cost');
    expect(within(cost).getByTestId('figure')).toHaveAttribute('data-provenance', 'measured');
    const findings = screen.getByTestId('entity-findings');
    for (const figure of within(findings).getAllByTestId('figure')) {
      expect(figure).toHaveAttribute('data-provenance', 'modelled');
    }
  });

  it('carries the risk verdict the home panel shows', async () => {
    // One module, one answer. A reader told a change is reversible here and permanent on the
    // home screen would be right to stop trusting both.
    renderEntity();
    const findings = await screen.findByTestId('entity-findings');
    expect(findings).toHaveTextContent('EBS_GP2_TO_GP3');
    expect(findings).toHaveTextContent('no regret');
    expect(findings).toHaveTextContent(/applied online and can be changed back/);
  });

  it('says how many findings could not be matched to any resource', async () => {
    // The second admission. A finding joins on the provider's identifier and the first party
    // sources do not always report the identifier Config recorded, so a short list here can
    // be nothing to do with this resource.
    renderEntity();
    const note = await screen.findByTestId('entity-unmatched');
    expect(note).toHaveTextContent('2 findings in this account could not be matched');
  });

  it('does not claim a clean resource when nothing could be joined', async () => {
    // The combination that would otherwise read as clean: no findings listed, and findings
    // in the account that joined to nothing. Both halves have to appear.
    renderEntity(withEntity({ findings: [] }));
    expect(await screen.findByTestId('entity-findings-empty')).toBeInTheDocument();
    expect(screen.getByTestId('entity-unmatched')).toHaveTextContent(/could not be matched/);
  });

  it('says nothing is unmatched by saying nothing, once there is nothing to say', async () => {
    renderEntity(withEntity({ unmatched_findings: 0 }));
    await screen.findByTestId('entity-findings');
    expect(screen.queryByTestId('entity-unmatched')).toBeNull();
  });

  it('names the relationship to each neighbour, with its direction', async () => {
    // Direction is most of the meaning. A subnet contained by a VPC and a VPC contained by a
    // subnet are not the same estate, and an undirected list would render both identically.
    renderEntity();
    const neighbours = await screen.findByTestId('entity-neighbours');
    expect(neighbours).toHaveTextContent('private-a');
    expect(neighbours).toHaveTextContent('CONTAINS');
    // And it links onward, because a neighbour is a resource with its own page.
    expect(within(neighbours).getByRole('link', { name: 'private-a' })).toHaveAttribute(
      'href',
      `/inventory/resources/${SUBNET}`,
    );
  });

  it('names the relationship that leaves what could be read', async () => {
    // The most interesting edge on the page and the one a neighbour list cannot show: the
    // far end is in an account nobody granted. A line to nowhere is not how to draw it.
    renderEntity();
    const boundary = await screen.findByTestId('entity-boundary');
    expect(boundary).toHaveTextContent('PEERS_WITH via ec2:DescribeVpcPeeringConnections');
    expect(boundary).toHaveTextContent(/account or region this read did not cover/);
  });

  it('does not claim a resource is absent when it may only be out of scope', async () => {
    // The API answers 404 for a node outside scope as well, deliberately, so this wording
    // cannot say the resource does not exist. Saying it did would tell a narrowed reader
    // that an account they were not granted holds nothing.
    renderEntity(null, '11111111-2222-3333-4444-555555555555');
    const missing = await screen.findByTestId('entity-not-found');
    expect(missing).toHaveTextContent(/may be in an account you were not granted/);
  });

  it('has no accessibility violations', async () => {
    const { container } = renderEntity();
    await screen.findByTestId('entity-neighbours');
    expect(await violationsIn(container)).toEqual([]);
  });

  describe('what manages it, FEAT-057', () => {
    it('names the address and the file when state owns it', async () => {
      // Both. The address is what FEAT-040 opens a pull request against, and the file is what a
      // reader opens, and an address with no file named tells them something unnamed owns it.
      renderEntity();
      const managed = await screen.findByTestId('entity-managed');
      expect(managed).toHaveTextContent('module.network.aws_vpc.main');
      expect(managed).toHaveTextContent('s3://fake-state/network.tfstate');
    });

    it('says not determined rather than unmanaged when it found nothing', async () => {
      // The claim this feature exists to protect. Unmanaged tells somebody to import a resource
      // or write it into code, and doing that to one already inside a module produces a
      // duplicate or a state conflict. The wording says what would make the answer possible.
      renderEntity(
        withEntity({
          management_state: 'NOT_DETERMINED',
          iac_address: null,
          iac_state_reference: null,
        }),
      );
      const unknown = await screen.findByTestId('entity-not-determined');
      expect(unknown).toHaveTextContent(/not the same as nothing managing it/);
      expect(unknown).toHaveTextContent(/only reads the state locations it is configured with/);
      expect(screen.queryByTestId('entity-unmanaged')).toBeNull();
    });

    it('says unmanaged is a claim, not an absence of one', async () => {
      // Reached only where an operator declared the account fully described and every location
      // was read. Saying so on the page is what lets a reader judge whether to trust it.
      renderEntity(
        withEntity({
          management_state: 'UNMANAGED',
          iac_address: null,
          iac_state_reference: null,
        }),
      );
      const unmanaged = await screen.findByTestId('entity-unmanaged');
      expect(unmanaged).toHaveTextContent(/declares this account fully described/);
      expect(unmanaged).toHaveTextContent(/a claim rather than an absence of one/);
      expect(screen.queryByTestId('entity-not-determined')).toBeNull();
    });
  });

  describe('what a change here can reach, FEAT-044', () => {
    it('says no score and names the slice when the graph has a hole in it', async () => {
      // The refusal is an answer, not an error. A radius computed from a graph missing a region
      // would look more contained than it is, in the one direction nobody checks.
      renderEntity();
      const refused = await screen.findByTestId('blast-refused');
      expect(refused).toHaveTextContent(/No score/);
      expect(refused).toHaveTextContent(/would look more contained than it is/);
      expect(refused).toHaveTextContent('fake-product-denied in fake-region-a is PARTIAL');
      expect(screen.queryByTestId('blast-radius')).toBeNull();
    });

    it('publishes the band with its parts and says the figure is a floor', async () => {
      // The band is what a reader scans and the parts are what they argue with. The floor
      // sentence is not a footnote: an infrastructure graph cannot see that one service reads
      // another's queue, so the real radius can only be larger than what is shown.
      const scored: ApiEnvelope<ApiBlastRadius> = {
        ...blastRadiusFixture(),
        data: {
          band: 'CROSS_ACCOUNT',
          parts: [
            {
              name: 'Resources reached',
              count: 4,
              why: 'Attached to the target, or to something that is.',
            },
            {
              name: 'Other accounts touched',
              count: 1,
              why: 'An estate whose owner has not been asked.',
            },
            {
              name: 'Dependencies that leave the graph',
              count: 2,
              why: 'Far ends nobody here can follow.',
            },
          ],
          reach: 4,
          accounts: 2,
          boundary_edges: 2,
          depth_bound_reached: false,
          is_lower_bound: true,
          refused_because: [],
          max_depth: 4,
        },
      };
      renderEntity(entityFixture(NODE), NODE, scored);
      expect(await screen.findByTestId('blast-band')).toHaveTextContent('CROSS_ACCOUNT');
      const panel = screen.getByTestId('blast-radius');
      expect(panel).toHaveTextContent(/At least this wide/);
      expect(panel).toHaveTextContent(/application level dependencies are invisible/);
      expect(panel).toHaveTextContent('Other accounts touched');
    });

    it('says so when the walk stopped at its depth bound', async () => {
      // The floor require_whole cannot catch. A walk that completed within its depth is bounded
      // rather than truncated, so nothing about it is incomplete and the resources beyond it
      // were never looked at.
      const bounded: ApiEnvelope<ApiBlastRadius> = {
        ...blastRadiusFixture(),
        data: {
          ...blastRadiusFixture().data,
          band: 'CONTAINED',
          parts: [{ name: 'Resources reached', count: 2, why: 'Attached to the target.' }],
          reach: 2,
          accounts: 1,
          boundary_edges: 0,
          depth_bound_reached: true,
          refused_because: [],
        },
      };
      renderEntity(entityFixture(NODE), NODE, bounded);
      expect(await screen.findByTestId('blast-radius')).toHaveTextContent(
        /stopped at its 4 hop bound/,
      );
    });
  });
});
