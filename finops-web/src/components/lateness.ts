/**
 * How late a collector is against its own cadence, as a pure number. FEAT-006.
 *
 * Its own module rather than a second export from `CadenceBar`, because a file that exports both
 * a component and a function cannot be hot reloaded, and because this is the part the screen
 * needs as well as the bar: the sentence above the table counts collectors past their cadence and
 * has to decide lateness exactly the way the drawing does. Two implementations would eventually
 * disagree, and a count saying one while the bars show two is the fault a reader finds first.
 */

/** How many times its own cadence a collector is behind, or null where that is not a number. */
export function latenessOf(
  ageSeconds: number | null,
  cadenceSeconds: number | null,
): number | null {
  if (ageSeconds === null || cadenceSeconds === null || cadenceSeconds <= 0) {
    return null;
  }
  return ageSeconds / cadenceSeconds;
}
