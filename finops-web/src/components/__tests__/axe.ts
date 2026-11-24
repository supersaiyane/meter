import axe from 'axe-core';

/**
 * Accessibility is asserted rather than reviewed.
 *
 * The `region` rule is disabled because it asks whether content sits inside a
 * landmark, which is a question about a page and not about a component rendered
 * on its own. Every other rule stays on, including the contrast and name rules
 * that matter most here.
 */
export async function violationsIn(container: HTMLElement): Promise<string[]> {
  const results = await axe.run(container, {
    rules: { region: { enabled: false } },
  });
  return results.violations.map((violation) => `${violation.id}: ${violation.help}`);
}
