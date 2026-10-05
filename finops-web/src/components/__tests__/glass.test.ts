import { describe, expect, it } from 'vitest';

import layout from '../../layout.css?raw';
import main from '../../main.tsx?raw';
import tokens from '../../tokens.css?raw';

/**
 * Glass that degrades, P8 spec section 5.1 and TASK-P8-001.
 *
 * The contrast test holds the colours. This holds the rules that decide which
 * colours apply: reduced transparency and a browser without backdrop-filter
 * get opaque panels and no glows, print gets the light theme with neither, and
 * the dark lengths, which light-dark() cannot carry, are declared once for each
 * way of choosing dark and held equal, because two blocks drift.
 */

/** The text inside the braces of the first block whose line starts with `prelude`. */
function block(css: string, prelude: string): string {
  const start = css.startsWith(prelude) ? 0 : css.indexOf(`\n${prelude}`);
  if (start < 0) {
    throw new Error(`no block starts with ${prelude}`);
  }
  const open = css.indexOf('{', start);
  let depth = 0;
  for (let at = open; at < css.length; at += 1) {
    if (css[at] === '{') {
      depth += 1;
    } else if (css[at] === '}') {
      depth -= 1;
      if (depth === 0) {
        return css.slice(open + 1, at);
      }
    }
  }
  throw new Error(`the block after ${prelude} never closes`);
}

function declarations(
  body: string,
  names: readonly string[],
): Readonly<Record<string, string>> {
  return Object.fromEntries(
    names.map((name) => [
      name,
      new RegExp(`${name}:\\s*([^;]+);`).exec(body)?.[1]?.trim() ?? '',
    ]),
  );
}

const SWAPPED_FOR_SOLID = [
  '--surface-raised: var(--surface-raised-solid)',
  '--surface-raised-2: var(--surface-raised-2-solid)',
  '--page-glow: none',
] as const;

const LENGTHS = ['--radius-card', '--panel-blur', '--panel-saturate'] as const;

describe('glass that degrades', () => {
  it('drops the glass and the glows when transparency is reduced', () => {
    const body = block(tokens, '@media (prefers-reduced-transparency: reduce)');
    for (const line of SWAPPED_FOR_SOLID) {
      expect(body).toContain(line);
    }
  });

  it('does the same in a browser without backdrop-filter', () => {
    const body = block(tokens, '@supports not');
    for (const line of SWAPPED_FOR_SOLID) {
      expect(body).toContain(line);
    }
  });

  it('prints in the light theme with no glass and no glows, whatever was chosen', () => {
    const body = block(tokens, '@media print');
    expect(body).toContain(":root[data-theme='dark']");
    expect(body).toContain('color-scheme: light');
    for (const line of SWAPPED_FOR_SOLID) {
      expect(body).toContain(line);
    }
    expect(body).toContain('backdrop-filter: none');
  });

  it('declares the light lengths by default and the dark ones the same way twice', () => {
    expect(declarations(block(tokens, ':root'), LENGTHS)).toEqual({
      '--radius-card': '18px',
      '--panel-blur': '22px',
      '--panel-saturate': '170%',
    });
    const fromTheSystem = declarations(
      block(tokens, '@media (prefers-color-scheme: dark)'),
      LENGTHS,
    );
    expect(fromTheSystem).toEqual({
      '--radius-card': '16px',
      '--panel-blur': '18px',
      '--panel-saturate': '140%',
    });
    expect(declarations(block(tokens, ":root[data-theme='dark']"), LENGTHS)).toEqual(
      fromTheSystem,
    );
  });

  it('blurs a panel by the tokens, so the fallback has one thing to switch off', () => {
    const panel = block(tokens, '.meter-panel');
    expect(panel).toContain('background: var(--surface-raised)');
    expect(panel).toContain(
      'backdrop-filter: blur(var(--panel-blur)) saturate(var(--panel-saturate))',
    );
  });

  it('paints the glows on the page and keeps the shell from covering them', () => {
    expect(block(layout, 'body')).toContain('background-image: var(--page-glow)');
    expect(block(layout, "[data-testid='shell'] > main")).toContain('background: transparent');
  });
});

describe('type', () => {
  it('sets Geist for text and Geist Mono for figures, both self hosted', () => {
    expect(tokens).toMatch(/--font-ui:\s*'Geist/);
    expect(tokens).toMatch(/--font-numeral:\s*'Geist Mono'/);
    expect(main).toContain('@fontsource/geist-sans');
    expect(main).toContain('@fontsource/geist-mono');
    expect(main).not.toContain('ibm-plex');
  });
});
