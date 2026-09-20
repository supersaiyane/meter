/**
 * Handing a string to the browser as a downloaded file.
 *
 * Its own module so the export screen can be tested without a DOM that supports
 * object URLs. jsdom has no `URL.createObjectURL`, so a screen that called it
 * inline would force every test of that screen to stub a global, and a stubbed
 * global is a thing tests forget to restore.
 *
 * It returns whether the save was attempted rather than throwing. A browser too old
 * for object URLs should leave the reader with a visible message, not a broken page,
 * and the screen is what decides what to say.
 */
export function saveFile(name: string, body: string, type = 'text/csv'): boolean {
  if (typeof URL.createObjectURL !== 'function') {
    return false;
  }
  const url = URL.createObjectURL(new Blob([body], { type }));
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = name;
  anchor.style.display = 'none';
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  // Released immediately. An object URL held after the click keeps the whole file in
  // memory for the life of the document, and this one is an entire billing period.
  URL.revokeObjectURL(url);
  return true;
}
