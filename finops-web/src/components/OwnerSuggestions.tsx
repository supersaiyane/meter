/**
 * Whom each source says to ask about a resource, strongest first. TASK-P11-005, ISS-021.
 *
 * A suggestion is never an owner. It sits under the owner cell, owned or not, and says where it
 * came from, the catalogue's application, the tag it was read from, or that the person or the
 * pipeline created the resource, so a reader can check it before asking anybody. A resource older
 * than CloudTrail's history says so rather than leaving the creator blank.
 */
import type { ApiOwnerSuggestion } from '../api/types';
import { suggestionText } from './displayNames';

export interface OwnerSuggestionsProps {
  /** The recommendation's id, for the test ids. */
  readonly id: string;
  readonly suggestions: readonly ApiOwnerSuggestion[];
  /** Where CloudTrail's history began when it found the resource older, or null. */
  readonly createdBefore: string | null;
}

export function OwnerSuggestions({ id, suggestions, createdBefore }: OwnerSuggestionsProps) {
  if (suggestions.length === 0 && createdBefore === null) {
    return null;
  }
  return (
    <ul aria-label="Whom to ask" data-testid={`owner-suggestions-${id}`}>
      {suggestions.map((one) => (
        <li key={`${one.source}-${one.owner}`} title={`As of ${one.as_of.slice(0, 10)}`}>
          {suggestionText(one)}
        </li>
      ))}
      {createdBefore === null ? null : (
        <li data-testid={`created-before-${id}`}>
          created before CloudTrail&apos;s 90 days, which begin {createdBefore.slice(0, 10)}
        </li>
      )}
    </ul>
  );
}
