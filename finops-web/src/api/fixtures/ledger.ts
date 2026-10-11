import type { ApiEnvelope, ApiLedger, ApiLedgerCredit, ApiLedgerCredits } from '../types';
import { meta } from './cost';

/**
 * The savings ledger, offline. FEAT-078, TASK-P11-008.
 *
 * It holds the cases the screen exists to render honestly: a team whose savings held two months,
 * a credit that regressed in its second month and stopped, a month the account's bill holds
 * nothing for, which carries no figure rather than a zero, and a credit no source named a team
 * for, verified with no month closed yet.
 */

const AS_OF = '2026-12-01T00:00:00Z';
const COLLECTED_AT = '2026-12-02T06:00:00Z';

function month(
  first: string,
  state: 'HELD' | 'REGRESSED' | 'UNOBSERVED',
  cost: string | null,
  saving: string | null,
) {
  return { month: first, state, cost, saving, as_of: AS_OF, collected_at: COLLECTED_AT };
}

const CREDITS: readonly ApiLedgerCredit[] = [
  {
    credit_id: '6a1f2b3c-4d5e-4f60-8a1b-2c3d4e5f6a70',
    recommendation_id: '4b5c6d7e-8f90-4b1c-8d2e-3f4a5b6c7d8e',
    account_id: 'fake-platform-a',
    resource_id: 'amazonec2/fake-platform-a/0002',
    team: 'platform',
    owner: 'platform@example.local',
    closed_by: 'alice',
    verified_monthly_saving: '40.00',
    verified_on: '2026-09-20',
    saving_held: '143.00',
    months_held: 2,
    regressed: false,
    months: [
      month('2026-10-01', 'HELD', '40.00', '53.00'),
      month('2026-11-01', 'HELD', '0.00', '90.00'),
    ],
    as_of: AS_OF,
    collected_at: COLLECTED_AT,
  },
  {
    credit_id: '7b2a3c4d-5e6f-4a71-9b2c-3d4e5f6a7b81',
    recommendation_id: '3a4b5c6d-7e8f-4a0b-9c1d-2e3f4a5b6c7d',
    account_id: 'fake-platform-a',
    resource_id: 'amazonec2/fake-platform-a/0003',
    team: 'platform',
    owner: 'platform@example.local',
    closed_by: 'bob',
    verified_monthly_saving: '25.00',
    verified_on: '2026-09-20',
    saving_held: '33.00',
    months_held: 1,
    regressed: true,
    months: [
      month('2026-10-01', 'HELD', '60.00', '33.00'),
      month('2026-11-01', 'REGRESSED', '120.00', '-30.00'),
    ],
    as_of: AS_OF,
    collected_at: COLLECTED_AT,
  },
  {
    credit_id: '8c3b4d5e-6f70-4b82-8c3d-4e5f6a7b8c92',
    recommendation_id: '5c6d7e8f-9012-4c2d-8e3f-4a5b6c7d8e9f',
    account_id: 'fake-product-b',
    resource_id: 'amazonrds/fake-product-b/0001',
    team: 'payments',
    owner: 'payments@example.local',
    closed_by: 'carol',
    verified_monthly_saving: '18.00',
    verified_on: '2026-09-20',
    saving_held: '0',
    months_held: 0,
    regressed: false,
    months: [month('2026-10-01', 'UNOBSERVED', null, null)],
    as_of: AS_OF,
    collected_at: COLLECTED_AT,
  },
  {
    credit_id: '9d4c5e6f-7081-4c93-9d4e-5f6a7b8c9da3',
    recommendation_id: '6d7e8f90-1234-4d3e-8f4a-5b6c7d8e9fa0',
    account_id: 'fake-product-b',
    resource_id: 'amazonec2/fake-product-b/0005',
    team: null,
    owner: 'dev.lead@fake.example',
    closed_by: 'dev.lead@fake.example',
    verified_monthly_saving: '12.00',
    verified_on: '2026-11-15',
    saving_held: '0',
    months_held: 0,
    regressed: false,
    months: [],
    as_of: AS_OF,
    collected_at: COLLECTED_AT,
  },
];

export function ledgerCreditsFixture(): ApiEnvelope<ApiLedgerCredits> {
  return { data: { team: null, every_team: true, credits: CREDITS }, meta: meta(2) };
}

export function ledgerFixture(): ApiEnvelope<ApiLedger> {
  return {
    data: {
      teams: [
        {
          team: 'platform',
          credits: 2,
          saving_held: '176.00',
          months_held: 3,
          regressed: 1,
          latest_month: '2026-11-01',
          as_of: AS_OF,
          collected_at: COLLECTED_AT,
        },
        {
          team: 'payments',
          credits: 1,
          saving_held: '0',
          months_held: 0,
          regressed: 0,
          latest_month: '2026-10-01',
          as_of: AS_OF,
          collected_at: COLLECTED_AT,
        },
        {
          team: null,
          credits: 1,
          saving_held: '0',
          months_held: 0,
          regressed: 0,
          latest_month: null,
          as_of: AS_OF,
          collected_at: COLLECTED_AT,
        },
      ],
    },
    meta: meta(2),
  };
}
