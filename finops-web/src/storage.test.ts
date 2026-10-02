import { afterEach, describe, expect, it } from 'vitest';

import { readStored, writeStored } from './storage';

/**
 * The reason this file exists. A browser that blocks site data throws on the
 * `window.localStorage` property access, before any key is named, and the
 * session token was read without a guard. The application did not start at all.
 *
 * Every case below is reachable in a real browser and none was covered, which
 * is why the fault was found by reading the code rather than by a failing test.
 */

const original = Object.getOwnPropertyDescriptor(window, 'localStorage');

function install(value: unknown): void {
  Object.defineProperty(window, 'localStorage', { value, configurable: true });
}

function installThrowing(): void {
  Object.defineProperty(window, 'localStorage', {
    get() {
      throw new Error('site data is blocked');
    },
    configurable: true,
  });
}

function workingStore(seed: Record<string, string> = {}) {
  const map = new Map(Object.entries(seed));
  return {
    getItem: (key: string) => map.get(key) ?? null,
    setItem: (key: string, value: string) => {
      map.set(key, value);
    },
    map,
  };
}

afterEach(() => {
  if (original) {
    Object.defineProperty(window, 'localStorage', original);
  }
});

describe('readStored', () => {
  it('returns the stored value', () => {
    install(workingStore({ 'meter.token': 'a-token' }));
    expect(readStored('meter.token')).toBe('a-token');
  });

  it('returns null for a key that was never set', () => {
    install(workingStore());
    expect(readStored('meter.token')).toBeNull();
  });

  it('returns null when the property access itself throws', () => {
    // This is the case that stopped the application starting. It is not a
    // missing key and not a null return: it is a throw on the access.
    installThrowing();
    expect(readStored('meter.token')).toBeNull();
  });

  it('returns null when storage is present but has no methods', () => {
    // Some environments substitute a plain object. Calling getItem on it throws
    // a TypeError further away than the cause, so it is treated as absent.
    install({});
    expect(readStored('meter.token')).toBeNull();
  });

  it('returns null when getItem itself throws', () => {
    install({
      getItem: () => {
        throw new Error('refused');
      },
    });
    expect(readStored('meter.token')).toBeNull();
  });
});

describe('writeStored', () => {
  it('writes the value', () => {
    const store = workingStore();
    install(store);
    writeStored('meter.nav', 'collapsed');
    expect(store.map.get('meter.nav')).toBe('collapsed');
  });

  it('says nothing when the write is refused', () => {
    // Quota exceeded and blocked site data both land here. Losing a preference
    // is not worth an exception every caller has to handle.
    install({
      getItem: () => null,
      setItem: () => {
        throw new Error('quota exceeded');
      },
    });
    expect(() => {
      writeStored('meter.nav', 'collapsed');
    }).not.toThrow();
  });

  it('says nothing when the property access throws', () => {
    installThrowing();
    expect(() => {
      writeStored('meter.nav', 'collapsed');
    }).not.toThrow();
  });
});
