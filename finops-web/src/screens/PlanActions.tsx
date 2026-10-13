import { useId, useState } from 'react';

import { reasonOf } from '../api/client';
import { usePlanStep, type PlanStep } from '../api/queries';
import type { ApiPlanStatus, ApiPurchasePlan } from '../api/types';

/**
 * A person's steps on Meter's purchase plan. FEAT-090, OPEN-36, TASK-P14-009.
 *
 * Meter records the decision and a person buys, constraint 6. Each step needs a note, because it
 * is a decision somebody may be asked about. Only the steps the plan's status allows are offered,
 * and the API and the database refuse any other; a refusal is shown in the API's own words.
 */

const STEPS: Readonly<Record<ApiPlanStatus, readonly PlanStep[]>> = {
  DRAFT: ['approve', 'withdraw'],
  APPROVED: ['bought', 'withdraw'],
  BOUGHT: [],
  VERIFIED: [],
  WITHDRAWN: [],
  LAPSED: [],
};

const LABELS: Readonly<Record<PlanStep, string>> = {
  approve: "Approve this month's tranche",
  bought: 'Record as bought',
  withdraw: 'Withdraw',
};

/** What there is to say about a plan nobody can move any further. */
const SETTLED: Readonly<Partial<Record<ApiPlanStatus, string>>> = {
  BOUGHT:
    'Recorded as bought. It is verified once the inventory holds each line it bought; a line ' +
    'not yet seen stays bought, never verified.',
  VERIFIED: 'Verified: every line it bought is a commitment the inventory holds.',
  WITHDRAWN: "Withdrawn. Next month's plan is drafted afresh.",
  LAPSED: 'Lapsed: nobody approved it within its month, and its usage is now a month old.',
};

export interface PlanActionsProps {
  readonly plan: ApiPurchasePlan;
  /** Whether this reader may take a step: a person whose scope is the whole organization. */
  readonly mayAct: boolean;
  /** Whether the plan buys anything this month; a plan that buys nothing cannot be approved. */
  readonly buysThisMonth: boolean;
}

export function PlanActions({ plan, mayAct, buysThisMonth }: PlanActionsProps) {
  const noteId = useId();
  const [note, setNote] = useState('');
  const step = usePlanStep();
  const offered = STEPS[plan.status].filter((one) => one !== 'approve' || buysThisMonth);

  if (!mayAct) {
    return (
      <p data-testid="plan-actions-refused">
        Only a person whose scope is the whole organization may approve, record or withdraw a
        plan, because a commitment is bought by the payer.
      </p>
    );
  }
  if (offered.length === 0) {
    return (
      <p data-testid="plan-actions-settled">
        {SETTLED[plan.status] ??
          'This plan buys nothing this month, so there is nothing to approve.'}
      </p>
    );
  }
  const ready = note.trim().length >= 3 && !step.isPending;
  return (
    <form
      data-testid="plan-actions"
      aria-label="Steps on this plan"
      onSubmit={(event) => {
        event.preventDefault();
      }}
    >
      {plan.status === 'APPROVED' ? (
        <p data-testid="plan-buy-note">
          Meter does not buy. Record the plan as bought once this month&apos;s lines are bought
          in AWS, and Meter verifies it against the inventory.
        </p>
      ) : null}
      <label htmlFor={noteId}>Why, for the record</label>
      <textarea
        id={noteId}
        value={note}
        maxLength={500}
        onChange={(event) => {
          setNote(event.target.value);
        }}
      />
      {offered.map((one) => (
        <button
          key={one}
          type="button"
          disabled={!ready}
          onClick={() => {
            step.mutate(
              { planId: plan.plan_id, step: one, note: note.trim() },
              {
                onSuccess: () => {
                  setNote('');
                },
              },
            );
          }}
        >
          {LABELS[one]}
        </button>
      ))}
      {step.isError ? (
        <p role="alert" data-testid="plan-step-refused">
          {reasonOf(step.error)}
        </p>
      ) : null}
    </form>
  );
}
