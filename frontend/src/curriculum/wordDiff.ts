export type DiffPart = { kind: 'same' | 'removed' | 'added'; text: string };

/** Words and the spaces between them, so that joining the parts gives the text back. */
function tokens(text: string): string[] {
  return text.match(/\s+|[^\s]+/g) ?? [];
}

/**
 * A word-by-word comparison of two wordings: what stays, what is removed from the old text and
 * what is added in the new one (longest common subsequence of the words, case-sensitive).
 * Whitespace differences alone are not changes.
 */
export function wordDiff(before: string, after: string): DiffPart[] {
  const a = tokens(before.trim()).filter((token) => !/^\s+$/.test(token));
  const b = tokens(after.trim()).filter((token) => !/^\s+$/.test(token));
  // lengths[i][j]: the longest common run of a[i..] and b[j..].
  const lengths: number[][] = Array.from({ length: a.length + 1 }, () =>
    new Array<number>(b.length + 1).fill(0)
  );
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      lengths[i][j] =
        a[i] === b[j] ? lengths[i + 1][j + 1] + 1 : Math.max(lengths[i + 1][j], lengths[i][j + 1]);
    }
  }
  const parts: DiffPart[] = [];
  const push = (kind: DiffPart['kind'], word: string) => {
    const last = parts[parts.length - 1];
    if (last && last.kind === kind) last.text += ` ${word}`;
    else parts.push({ kind, text: word });
  };
  let i = 0;
  let j = 0;
  while (i < a.length || j < b.length) {
    if (i < a.length && j < b.length && a[i] === b[j]) {
      push('same', a[i]);
      i++;
      j++;
    } else if (j < b.length && (i === a.length || lengths[i][j + 1] > lengths[i + 1][j])) {
      push('added', b[j]);
      j++;
    } else {
      push('removed', a[i]);
      i++;
    }
  }
  return parts;
}
