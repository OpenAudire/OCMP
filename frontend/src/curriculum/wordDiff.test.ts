import { describe, expect, it } from 'vitest';

import { wordDiff } from './wordDiff';

describe('wordDiff', () => {
  it('shows one word replaced', () => {
    expect(wordDiff('Understand the cardiac cycle.', 'Describe the cardiac cycle.')).toEqual([
      { kind: 'removed', text: 'Understand' },
      { kind: 'added', text: 'Describe' },
      { kind: 'same', text: 'the cardiac cycle.' },
    ]);
  });

  it('shows words added and words removed', () => {
    expect(wordDiff('Know the heart well', 'Name the chambers of the heart')).toEqual([
      { kind: 'removed', text: 'Know' },
      { kind: 'added', text: 'Name' },
      { kind: 'same', text: 'the' },
      { kind: 'added', text: 'chambers of the' },
      { kind: 'same', text: 'heart' },
      { kind: 'removed', text: 'well' },
    ]);
  });

  it('is empty of changes for the same words, whatever the spacing', () => {
    expect(wordDiff('Name  the\nbones.', 'Name the bones.')).toEqual([
      { kind: 'same', text: 'Name the bones.' },
    ]);
  });

  it('treats a changed capital as a change', () => {
    expect(wordDiff('name the bones', 'Name the bones')).toEqual([
      { kind: 'removed', text: 'name' },
      { kind: 'added', text: 'Name' },
      { kind: 'same', text: 'the bones' },
    ]);
  });

  it('handles empty text on either side', () => {
    expect(wordDiff('', 'Name it')).toEqual([{ kind: 'added', text: 'Name it' }]);
    expect(wordDiff('Name it', '')).toEqual([{ kind: 'removed', text: 'Name it' }]);
    expect(wordDiff('', '')).toEqual([]);
  });

  it('putting the parts together in order gives back both texts', () => {
    const before = 'Be aware of the ethical issues in practice';
    const after = 'Identify ethical issues in clinical practice';
    const parts = wordDiff(before, after);
    const rebuild = (skip: 'added' | 'removed') =>
      parts
        .filter((part) => part.kind !== skip)
        .map((part) => part.text)
        .join(' ');
    expect(rebuild('added')).toBe(before);
    expect(rebuild('removed')).toBe(after);
  });
});
