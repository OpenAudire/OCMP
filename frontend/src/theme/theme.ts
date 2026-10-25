import {
  createTheme,
  defaultVariantColorsResolver,
  parseThemeColor,
  rem,
  type CSSVariablesResolver,
  type MantineColorsTuple,
  type VariantColorsResolver,
} from '@mantine/core';

import { darkTokens, lightTokens, sidebarTokens, tokenVariables } from './tokens';

/** Teal around the light (shade 7) and dark (shade 4) brand colours. */
const brand: MantineColorsTuple = [
  '#E1F0EE',
  '#C3E3DF',
  '#9DD2CC',
  '#72BFB8',
  '#45B5AD',
  '#2A9690',
  '#177A79',
  '#0E6B6B',
  '#0A5656',
  '#063F40',
];

/**
 * Mantine's neutral palettes rebuilt from the tokens, so component defaults that use
 * them directly (gray-4 / dark-4 input and default borders, placeholders) match the
 * design and meet 3:1 for field borders.
 */
const gray: MantineColorsTuple = [
  lightTokens.bg,
  lightTokens.soft,
  lightTokens.line,
  lightTokens.line,
  lightTokens.fieldLine,
  lightTokens.faint,
  lightTokens.muted,
  '#3E4A54',
  '#2A3640',
  lightTokens.ink,
];

const dark: MantineColorsTuple = [
  darkTokens.ink,
  '#C3D0D1',
  darkTokens.muted,
  darkTokens.faint,
  darkTokens.fieldLine,
  darkTokens.line,
  darkTokens.soft,
  darkTokens.surface,
  darkTokens.bg,
  '#0A1012',
];

const FONT_SANS = "'IBM Plex Sans', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif";
const FONT_MONO = "'IBM Plex Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace";

/**
 * Filled brand and red (delete) buttons use the scheme's on-brand text (white in light,
 * dark ink in dark): the dark scheme's brand and bad colours are light.
 */
const variantColorResolver: VariantColorsResolver = (input) => {
  const colors = defaultVariantColorsResolver(input);
  const parsed = parseThemeColor({ color: input.color || input.theme.primaryColor, theme: input.theme });
  const onToken = parsed.color === 'brand' || parsed.color === 'red';
  if (input.variant === 'filled' && onToken && parsed.shade === undefined) {
    return { ...colors, color: 'var(--cic-on-brand)' };
  }
  return colors;
};

export const theme = createTheme({
  colors: { brand, gray, dark },
  primaryColor: 'brand',
  primaryShade: { light: 7, dark: 4 },
  white: lightTokens.surface,
  black: lightTokens.ink,
  variantColorResolver,
  fontFamily: FONT_SANS,
  fontFamilyMonospace: FONT_MONO,
  headings: {
    fontFamily: FONT_SANS,
    fontWeight: '600',
    sizes: {
      h1: { fontSize: rem(30), lineHeight: '1.2' },
      h2: { fontSize: rem(19), lineHeight: '1.3' },
      h3: { fontSize: rem(16), lineHeight: '1.4' },
    },
  },
  radius: { xs: rem(4), sm: rem(6), md: rem(10), lg: rem(14), xl: rem(16) },
  defaultRadius: 'md',
  focusRing: 'auto',
  components: {
    Paper: { defaultProps: { radius: 'lg' } },
  },
});

/** Semantic Mantine variables that point at the tokens (same in both schemes). */
const mantineVariables: Record<string, string> = {
  '--mantine-color-body': 'var(--cic-bg)',
  '--mantine-color-text': 'var(--cic-ink)',
  '--mantine-color-bright': 'var(--cic-ink)',
  '--mantine-color-dimmed': 'var(--cic-muted)',
  '--mantine-color-placeholder': 'var(--cic-faint)',
  '--mantine-color-anchor': 'var(--cic-brand-ink)',
  '--mantine-color-error': 'var(--cic-bad)',
  '--mantine-color-success': 'var(--cic-ok)',
  '--mantine-color-default': 'var(--cic-surface)',
  '--mantine-color-default-hover': 'var(--cic-soft)',
  '--mantine-color-default-color': 'var(--cic-ink)',
  '--mantine-color-default-border': 'var(--cic-field-line)',
  ...Object.fromEntries(
    ['--mantine-primary-color', '--mantine-color-brand'].flatMap((name) => [
      [`${name}-filled`, 'var(--cic-brand)'],
      [`${name}-filled-hover`, 'var(--cic-brand-hover)'],
      [`${name}-light`, 'var(--cic-brand-soft)'],
      [`${name}-light-hover`, 'color-mix(in srgb, var(--cic-brand-soft), var(--cic-brand) 12%)'],
      [`${name}-light-color`, 'var(--cic-brand-ink)'],
      [`${name}-outline`, 'var(--cic-brand-ink)'],
    ])
  ),
  '--mantine-primary-color-contrast': 'var(--cic-on-brand)',
  // Errors (Alert color="red", error text) use the bad tokens, which meet AA.
  '--mantine-color-red-filled': 'var(--cic-bad)',
  // Hover moves towards the ink colour, which keeps the on-brand text readable.
  '--mantine-color-red-filled-hover': 'color-mix(in srgb, var(--cic-bad) 88%, var(--cic-ink))',
  '--mantine-color-red-light': 'var(--cic-bad-soft)',
  '--mantine-color-red-light-color': 'var(--cic-bad)',
  '--mantine-color-red-text': 'var(--cic-bad)',
};

export const cssVariablesResolver: CSSVariablesResolver = () => ({
  variables: tokenVariables(sidebarTokens, 'sidebar'),
  light: { ...tokenVariables({ ...lightTokens }), ...mantineVariables },
  dark: { ...tokenVariables({ ...darkTokens }), ...mantineVariables },
});
