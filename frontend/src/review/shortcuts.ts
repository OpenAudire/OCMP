/**
 * Keyboard shortcuts of the review queue (ADR 040).
 *
 * Single-character shortcuts must not catch people by surprise (WCAG 2.1.4), so they work
 * only while focus is inside the queue (the list and the details), never in a text field,
 * with no Ctrl, Alt or Meta key held, and they can be turned off for good with the switch
 * on the page (kept in this browser). Every action is also a button.
 */
export type ShortcutAction = 'accept' | 'reject' | 'edit' | 'skip' | 'second';

const KEY_ACTIONS: Record<string, ShortcutAction> = {
  a: 'accept',
  r: 'reject',
  e: 'edit',
  s: 'skip',
  '2': 'second',
};

/** The keys, in the order the legend shows them. */
export const SHORTCUT_KEYS: readonly { key: string; action: ShortcutAction }[] = [
  { key: 'A', action: 'accept' },
  { key: 'R', action: 'reject' },
  { key: 'E', action: 'edit' },
  { key: 'S', action: 'skip' },
  { key: '2', action: 'second' },
];

const STORAGE_KEY = 'cic.review.shortcuts';

export function readShortcutsOn(): boolean {
  try {
    return window.localStorage.getItem(STORAGE_KEY) !== 'off';
  } catch {
    return true;
  }
}

export function saveShortcutsOn(on: boolean): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, on ? 'on' : 'off');
  } catch {
    // Storage may be blocked; the choice then lasts until the page is closed.
  }
}

interface KeyInput {
  key: string;
  ctrlKey: boolean;
  altKey: boolean;
  metaKey: boolean;
  shiftKey: boolean;
  repeat: boolean;
}

/** Text a person types into: letters there are never shortcuts. */
function isTextEntry(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  if (target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement) return true;
  if (target instanceof HTMLInputElement) {
    return !['radio', 'checkbox', 'button', 'submit', 'reset'].includes(target.type);
  }
  return false;
}

/** The action a key press stands for, or null when it is not a shortcut right now. */
export function shortcutFor(event: KeyInput, target: EventTarget | null): ShortcutAction | null {
  if (event.ctrlKey || event.altKey || event.metaKey || event.shiftKey || event.repeat) return null;
  if (isTextEntry(target)) return null;
  return KEY_ACTIONS[event.key.toLowerCase()] ?? null;
}
