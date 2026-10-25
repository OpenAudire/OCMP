# ADR 026: Visual Design, Theming and Accessibility Checks

## Status

Accepted (2026-10-25, Slice 1.1)

## Context

The Phase 1 mockups (`docs/mockups/`) define design tokens for a light and a dark theme,
IBM Plex type, a dark teal sidebar, 44px controls and empty, loading and error states.
Mantine (ADR 002) has its own palettes and CSS variables; its defaults (for example
`red.6` text, `gray.4` borders) do not all meet WCAG 2.2 AA, and its dark theme uses a
neutral grey palette. The brief (section 11) requires WCAG 2.2 AA in both themes, and the
Phase 1 decisions require self-hosted fonts (decision 9), darker light-theme hint text and
a 3:1 border for fields (decision 1).

## Decision

### Tokens
- One source: `frontend/src/theme/tokens.ts` holds the light, dark and sidebar tokens.
  The theme's CSS variables resolver writes them as `--cic-*` variables per colour scheme
  (`--cic-bg`, `--cic-brand-ink`, `--cic-field-line`, `--cic-sidebar-bg`, ...).
- Mantine is mapped onto the tokens rather than styled per component: its semantic
  variables (body, text, dimmed, placeholder, anchor, error, default border, primary
  colour variants, red variants) point at `--cic-*`; the `gray` and `dark` palettes are
  rebuilt from the tokens; `brand` (teal) is the primary colour, shade 7 in light and 4 in
  dark; filled brand buttons use `--cic-on-brand` text. `src/theme/global.css` sets what
  the theme object cannot: 44px buttons and fields at the default sizes, card surface and
  border, menu colours.
- Changes from the mockups: light `faint` `#5F6B76` (was `#6B7782`, 4.26:1 on `bg`); new
  `fieldLine` `#7F8A93` light / `#667A7D` dark (at least 3:1 on every background);
  `brandHover` and the sidebar hover colour added. A unit test checks every text token at
  4.5:1 and field borders at 3:1 on `bg`, `surface` and `soft`, in both themes.
- Colour rule from the mockups: teal means good, selected or primary; ochre means "needs
  attention" only; every coloured state also has a text label.

### Type
IBM Plex Sans (400-700) and IBM Plex Mono (400, 500) from the `@fontsource` packages (SIL
Open Font License), bundled by Vite and served by this site: no requests to font services.
System fonts are the fallback.

### Colour scheme
The scheme follows the system until the person uses the header toggle; Mantine keeps the
choice in local storage. `public/color-scheme.js` (an external file, so a strict
Content-Security-Policy can allow it) applies it before the app loads, so there is no
flash of the light theme.

### Shared layout and components
- `layout/`: dark teal sidebar (wordmark, icon navigation with the review queue as a
  sub-item and a count slot whose number also has a text label, institution name), header
  (theme toggle, account menu with initials). On phones the sidebar opens from the menu
  button and is hidden (`visibility: hidden`) when closed, so it is not reachable by
  keyboard or screen readers.
- `ui/`: `Page` (padding and the page's only `h1`) and `EmptyState`, `LoadingState`,
  `ErrorState` from the States mockup. Error states use `role="alert"`; loading states are
  `aria-busy` with a labelled progress bar or a status message.

### Accessibility checks in end-to-end tests
Playwright (`frontend/e2e/`) runs each journey in a light and a dark project and checks
pages with axe-core (`@axe-core/playwright`, WCAG 2.0-2.2 A and AA rules). The tests run
against the Docker Compose stack, locally and in CI (job "End-to-End Tests"), after one
sign-in whose session is reused, because the API rate-limits sign-ins.

## Consequences

- New components use `var(--cic-*)` and Mantine props, never raw colours; new pages wrap
  their content in `Page` and use the shared states.
- Mantine components that read palette slots directly may need a mapping in
  `global.css`; axe in both themes is the check (it found the menu hover colour and the
  menu's focus placeholder in this slice).
- Mantine's `Menu` needs `withInitialFocusPlaceholder={false}`: its placeholder breaks the
  `menu` role's required children.
- CI starts the full stack for the end-to-end job (a few minutes per run).
