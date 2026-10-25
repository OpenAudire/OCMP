# Curriculum in Context – approved screen mockups

These files are the approved UI reference for Phase 1. They were made in a design tool, so they won't open as normal web pages (each needs the tool's runtime). Read them as **source**: the markup shows layout and content, the `<style>` block shows the design tokens, and the `<script>` block shows the interactive behaviour and demo data.

All names, numbers and objectives are fictional demo data.

## Screens

| File | Screen | Key points |
|---|---|---|
| `Dashboard.dc.html` | Committee dashboard | 4 KPI cards with 8-week trend lines; traceability diagram (programme outcome → module outcomes → session objectives → framework items); weighted coverage this year vs last year; declared vs delivered; mapping progress; credit and notional-hours table |
| `Builder.dc.html` | Curriculum builder | Structure tree; learning event details; objective cards with quality-checker flags (vague verb + suggested rewrite, two verbs, near-duplicate); tags with inheritance note; module credit check; Brightspace link |
| `Workspace.dc.html` | Mapping workspace | Three panes: objectives list with mapped/suggested/unmapped dots; selected objective with linked items (coverage 0–5 shown as 5 segments, depth, status); framework tree with Link buttons and "mapped from N objectives" |
| `Main.dc.html` | AI mapping review queue | Progress card; suggestion cards with confidence bars; detail panel with evidence quote highlighted, rationale, coverage 0–5 and depth pickers, Accept / Second review / Reject with keyboard shortcuts |
| `Coverage.dc.html` | Coverage report | Four method cards (single, multiple, subordinate, weighted) switch the heatmap; warning note on overstated counts; heatmap groups × years with <30% cells outlined in ochre; biggest gaps list |
| `Frameworks.dc.html` | Framework library | Cards per framework with type and status (Active / Needs content / Not loaded); detail panel with stats, structure and coverage bars; template notice for copyrighted frameworks; versions and crosswalk panel |
| `Import.dc.html` | Excel import preview | 3-step progress; file summary (ready / warnings / errors); filter tabs; row table with result and plain-language message; dry-run toggle; error report download |
| `States.dc.html` | Empty, loading and error states | Empty: "No modules yet" with import options. Loading: AI run progress with skeletons. Error: AI service unreachable, explaining nothing was lost |
| `Dark.dc.html` | Dark mode | The dashboard rendered with the dark theme |
| `Student.dc.html` | Student explorer (phone, 390×844) | This week's sessions; upcoming block test and what it covers; where Year 2 builds each competency; bottom tab bar |
| `Sidebar.dc.html` | Shared sidebar | Two-tone wordmark "Curriculum" / "in Context"; icon navigation; Review queue as a sub-item with an ochre count badge; active item has an ochre left bar |

## Design tokens

Defined as CSS variables on `.cic` (light) and `.cic.dark` (dark) in the mockups. The app implements them in `frontend/src/theme/tokens.ts` as `--cic-*` variables (ADR 026); this table matches the app:

| Token | Light | Dark | Use |
|---|---|---|---|
| `--bg` | `#F5F7F6` | `#0E1618` | Page background |
| `--surface` | `#FFFFFF` | `#152024` | Cards, header |
| `--ink` | `#15212A` | `#E6EEEE` | Main text |
| `--muted` | `#55616C` | `#A3B3B5` | Secondary text |
| `--faint` | `#5F6B76` | `#8D9EA1` | Hints (light darkened from `#6B7782` in Phase 1: 4.26:1 on `--bg`) |
| `--line` | `#DCE2E5` | `#283639` | Card and divider borders (decorative) |
| `--field-line` | `#7F8A93` | `#667A7D` | Borders of inputs and toggles (at least 3:1, added in Phase 1) |
| `--soft` | `#EEF2F2` | `#1C2A2D` | Tracks, chips, subtle fills |
| `--brand` | `#0E6B6B` | `#45B5AD` | Primary actions, accepted, good |
| `--brand-ink` | `#0A5656` | `#86D6CF` | Brand-coloured text and links |
| `--brand-soft` | `#E1F0EE` | `#173634` | Selected and accepted backgrounds |
| `--on-brand` | `#FFFFFF` | `#0E1618` | Text on brand buttons |
| `--warm` | `#A3561A` | `#E39A57` | Ochre accent: needs attention only |
| `--warm-ink` | `#8A4510` | `#F2B57C` | Ochre text |
| `--warm-soft` | `#FBEEDF` | `#38281A` | Warning and gap backgrounds |
| `--warm-line` | `#EFCFAE` | `#5A3F26` | Warning borders |
| `--bad` | `#9B2C2C` | `#F19191` | Errors, reject |
| `--bad-soft` | `#FBEAEA` | `#3A2020` | Error backgrounds |
| `--ok` | `#1F7A4D` | `#6CCB98` | Positive trends |
| `--ok-soft` | `#E4F3EA` | `#183126` | Positive backgrounds |

- Sidebar: always `#0F2A2E`, text `#C9DCDA`, active background `#1F4D53`, ochre highlight `#E8B07A`.
- Type: IBM Plex Sans (UI) and IBM Plex Mono (codes, numbers in tables). Page titles 30px/600, section titles 19px/600, body 14–16px.
- Shape: cards 14px radius with a soft shadow in light mode and none in dark; buttons and fields 10px radius and at least 44px tall.
- Colour rule: teal means good, selected or primary. Ochre means "needs attention" (gaps, warnings, second review, below 40% coverage). Never rely on colour alone: every coloured state also has a label.
