import { describe, expect, it } from 'vitest';

import { darkTokens, lightTokens, sidebarTokens, tokenVariables, type ColorTokens } from './tokens';

/** WCAG 2.2 contrast ratio of two #RRGGBB colours. */
function contrast(a: string, b: string): number {
  const luminance = (hex: string) => {
    const [r, g, bl] = [1, 3, 5].map((i) => {
      const c = parseInt(hex.slice(i, i + 2), 16) / 255;
      return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * r + 0.7152 * g + 0.0722 * bl;
  };
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

const TEXT: (keyof ColorTokens)[] = ['ink', 'muted', 'faint', 'brandInk', 'warmInk', 'bad', 'ok'];
const BACKGROUNDS: (keyof ColorTokens)[] = ['bg', 'surface', 'soft'];

describe.each([
  ['light', lightTokens],
  ['dark', darkTokens],
])('%s tokens', (_name, tokens) => {
  it.each(TEXT)('%s text meets 4.5:1 on every background', (text) => {
    for (const background of BACKGROUNDS) {
      expect(contrast(tokens[text], tokens[background])).toBeGreaterThanOrEqual(4.5);
    }
  });

  it('field borders meet 3:1 (WCAG 1.4.11)', () => {
    for (const background of BACKGROUNDS) {
      expect(contrast(tokens.fieldLine, tokens[background])).toBeGreaterThanOrEqual(3);
    }
  });

  it('text on filled brand, soft brand, warning and error fills meets 4.5:1', () => {
    expect(contrast(tokens.onBrand, tokens.brand)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(tokens.onBrand, tokens.brandHover)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(tokens.brandInk, tokens.brandSoft)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(tokens.warmInk, tokens.warmSoft)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(tokens.bad, tokens.badSoft)).toBeGreaterThanOrEqual(4.5);
  });
});

describe('sidebar tokens', () => {
  it('meet 4.5:1 for every text colour', () => {
    expect(contrast(sidebarTokens.text, sidebarTokens.bg)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(sidebarTokens.text, sidebarTokens.hoverBg)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(sidebarTokens.textActive, sidebarTokens.activeBg)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(sidebarTokens.note, sidebarTokens.bg)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(sidebarTokens.accent, sidebarTokens.bg)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(sidebarTokens.bg, sidebarTokens.accent)).toBeGreaterThanOrEqual(4.5);
  });
});

describe('token variables', () => {
  it('become kebab-case CSS variables', () => {
    expect(tokenVariables({ fieldLine: '#000' })).toEqual({ '--cic-field-line': '#000' });
    expect(tokenVariables({ activeBg: '#111' }, 'sidebar')).toEqual({
      '--cic-sidebar-active-bg': '#111',
    });
  });
});
