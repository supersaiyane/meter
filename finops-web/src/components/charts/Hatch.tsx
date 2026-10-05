/**
 * The hatch a modelled mark is drawn under, once per chart. In the text colour rather than
 * the series colour, so one pattern serves every series and reads in both themes.
 */
export function Hatch({ id }: { readonly id: string }) {
  return (
    <defs>
      <pattern
        id={`${id}-hatch`}
        width="4"
        height="4"
        patternUnits="userSpaceOnUse"
        patternTransform="rotate(45)"
      >
        <line x1="0" y1="0" x2="0" y2="4" stroke="currentColor" strokeWidth="1.5" />
      </pattern>
    </defs>
  );
}
