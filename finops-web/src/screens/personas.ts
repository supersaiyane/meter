import { readStored, writeStored } from '../storage';

/**
 * The three dashboards on the Overview, FEAT-070 and P8 spec section 5.8, and the reader's last
 * choice of them, remembered in their browser beside the theme and the rail.
 *
 * The FinOps practitioner's dashboard is the one drawn on 2026-10-05, so it is the one a reader
 * who has chosen nothing opens on, with the other two a click away.
 */

export type Persona = 'finops' | 'executive' | 'engineering';

export const PERSONAS: readonly { readonly id: Persona; readonly label: string }[] = [
  { id: 'finops', label: 'FinOps practitioner' },
  { id: 'executive', label: 'Executive' },
  { id: 'engineering', label: 'Engineering lead' },
];

export const PERSONA_KEY = 'meter.persona';

export const DEFAULT_PERSONA: Persona = 'finops';

function isPersona(value: string | null): value is Persona {
  return PERSONAS.some((persona) => persona.id === value);
}

/** What was chosen before, and the drawn dashboard when nothing was or the value is unknown. */
export function storedPersona(): Persona {
  const value = readStored(PERSONA_KEY);
  return isPersona(value) ? value : DEFAULT_PERSONA;
}

export function choosePersona(persona: Persona): void {
  writeStored(PERSONA_KEY, persona);
}
