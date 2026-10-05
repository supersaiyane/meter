/**
 * Handing a file the server wrote to the browser as a download. FEAT-067.
 *
 * Its own module so the Export menu can be tested without a DOM that supports object URLs.
 * jsdom has no `URL.createObjectURL`, so a component that called it inline would force every
 * test of it to stub a global, and a stubbed global is a thing tests forget to restore.
 *
 * It returns whether the save was attempted rather than throwing. A browser too old for object
 * URLs should leave the reader with a visible message, not a broken page, and the menu is what
 * decides what to say.
 */
export function saveFile(name: string, body: Blob): boolean {
  if (typeof URL.createObjectURL !== 'function') {
    return false;
  }
  const url = URL.createObjectURL(body);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = name;
  anchor.style.display = 'none';
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  // Released immediately. An object URL held after the click keeps the whole file in memory
  // for the life of the document, and this one can be a hundred thousand rows.
  URL.revokeObjectURL(url);
  return true;
}
