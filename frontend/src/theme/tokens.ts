/**
 * Design tokens from the approved mockups (docs/mockups/README.md), with the Phase 1
 * contrast changes: light `faint` darkened, `fieldLine` added for inputs and toggles.
 *
 * They become CSS variables (`--cic-bg`, `--cic-brand-ink`, ...) for each colour scheme
 * through the theme's CSS variables resolver, so CSS modules use `var(--cic-...)`.
 * Colour rule: brand (teal) means good, selected or primary; warm (ochre) means
 * "needs attention" only; every coloured state also has a text label.
 */
export interface ColorTokens {
  bg: string;
  surface: string;
  ink: string;
  muted: string;
  faint: string;
  line: string;
  fieldLine: string;
  soft: string;
  brand: string;
  brandHover: string;
  brandInk: string;
  brandSoft: string;
  onBrand: string;
  warm: string;
  warmInk: string;
  warmSoft: string;
  warmLine: string;
  bad: string;
  badSoft: string;
  ok: string;
  okSoft: string;
  shadow: string;
}

export const lightTokens: ColorTokens = {
  bg: '#F5F7F6',
  surface: '#FFFFFF',
  ink: '#15212A',
  muted: '#55616C',
  faint: '#5F6B76',
  line: '#DCE2E5',
  fieldLine: '#7F8A93',
  soft: '#EEF2F2',
  brand: '#0E6B6B',
  brandHover: '#0A5656',
  brandInk: '#0A5656',
  brandSoft: '#E1F0EE',
  onBrand: '#FFFFFF',
  warm: '#A3561A',
  warmInk: '#8A4510',
  warmSoft: '#FBEEDF',
  warmLine: '#EFCFAE',
  bad: '#9B2C2C',
  badSoft: '#FBEAEA',
  ok: '#1F7A4D',
  okSoft: '#E4F3EA',
  shadow: '0 1px 2px rgba(16, 33, 42, 0.05), 0 6px 20px rgba(16, 33, 42, 0.05)',
};

export const darkTokens: ColorTokens = {
  bg: '#0E1618',
  surface: '#152024',
  ink: '#E6EEEE',
  muted: '#A3B3B5',
  faint: '#8D9EA1',
  line: '#283639',
  fieldLine: '#667A7D',
  soft: '#1C2A2D',
  brand: '#45B5AD',
  brandHover: '#5EC4BC',
  brandInk: '#86D6CF',
  brandSoft: '#173634',
  onBrand: '#0E1618',
  warm: '#E39A57',
  warmInk: '#F2B57C',
  warmSoft: '#38281A',
  warmLine: '#5A3F26',
  bad: '#F19191',
  badSoft: '#3A2020',
  ok: '#6CCB98',
  okSoft: '#183126',
  shadow: 'none',
};

/** The sidebar is dark teal in both themes. */
export const sidebarTokens = {
  bg: '#0F2A2E',
  text: '#C9DCDA',
  textActive: '#FFFFFF',
  activeBg: '#1F4D53',
  hoverBg: '#173C41',
  accent: '#E8B07A',
  divider: '#23464B',
  note: '#9DBAB7',
};

/** `fieldLine` becomes `--cic-field-line`; with prefix `sidebar`, `bg` becomes `--cic-sidebar-bg`. */
function cssName(key: string, prefix: string): string {
  const name = prefix ? `${prefix}-${key}` : key;
  return `--cic-${name.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`)}`;
}

export function tokenVariables(
  tokens: Readonly<Record<string, string>>,
  prefix = ''
): Record<string, string> {
  return Object.fromEntries(
    Object.entries(tokens).map(([key, value]) => [cssName(key, prefix), value])
  );
}
