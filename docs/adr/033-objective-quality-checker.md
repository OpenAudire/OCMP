# ADR 033: Objective Quality Checker and Taxonomy Level Suggestion (Rule Based)

## Status

Accepted (Slice 1.7). Builds on ADR 013 (objectives and taxonomy), ADR 031 (objective
editing) and ADR 027 (who sees what).

## Context

The brief (section 7, "Objective quality checker") asks for flags on vague verbs, several
verbs in one objective, a missing domain, a missing upward link and very long wording, and
a taxonomy level suggested from the verb using the scale's verb lists, "rule-based first".
It runs as you type and in bulk. Near-duplicate detection (embeddings) and AI rewriting come
in later slices (1.15, 1.17).

**Update, Slice 1.15 (ADR 044).** The pure rules above are unchanged and the live check stays
rule-based. The bulk check (`Check wording`) now also reports `near_duplicate` (a note, from stored
embeddings, only while embeddings are on) and `possible_personal_information` (a warning, from the
privacy detectors, kinds only). They are added by `objective_checks.check_version`, not by
`check_objective`.

## Decision

### Rules, not AI
Everything is plain code in `app/services/objective_quality.py` (pure functions, no
database, no network). Nothing is sent to any AI provider and nothing is saved by a check.
Findings are advice: they never block saving.

### Findings
Each finding has a `code`, a `severity` (`warning` or `info`), a `message_key` and a
`suggestion_key` (frontend translation keys `curriculum.quality.<code>.message` and
`.suggestion`) and `params` for the text (the verbs found, a count).

| Code | Severity | Fires when |
|---|---|---|
| `vague_verb` | warning | The leading verb, or a verb after "and", "or" or a comma, is vague (understand, know, appreciate, "be aware of", "learn about"...) |
| `multiple_verbs` | warning | More than one known verb leads a clause ("Identify the organelles and state their functions") |
| `too_long` | warning | More than 40 words |
| `missing_domain` | warning | No domain set |
| `missing_upward_link` | warning | A module outcome or session objective has no upward link (skipped when unknown) |
| `no_action_verb` | info | The first word is not a verb the checker knows |
| `too_short` | info | Fewer than 3 words |
| `learner_framing` | info | Starts "Students will be able to..." (the lead-in is stripped before the other rules) |
| `ambiguous_qualifier` | info | Words such as appropriate, adequate, various, "a range of" |
| `level_differs` | info | The chosen level is in a scale where the leading verb points elsewhere |

Words that are also common nouns (use, plan, state, list...) count as a second verb only
before a determiner ("and use the...") to keep false alarms down.

### Verb lists and languages
- **Verbs per taxonomy level** are the existing `taxonomy_levels.verbs` (pack format, ADR
  014), so any imported or demo scale brings its own lists; nothing is copied into code. A
  verb can belong to several levels and scales; the suggestion lists each.
- **Wording rules** (vague verbs and phrases, qualifiers, lead-ins, thresholds, extra
  measurable verbs that belong to no level) are versioned data files per language,
  `app/services/objective_rules/<code>.json`, with a `version` the bulk response returns.
  Only English exists; a new language is a new file with the same keys. An unknown language
  falls back to English. Verb matching accepts simple inflections (explains, analysing) and
  British and American spellings (analyse, analyze).

### Level suggestion
The leading verb (after any lead-in) is looked up in every level's verb list. The response
lists the matching levels (`taxonomy_level_id`, level and scale names). The editor shows them
as buttons ("Use Understand (Bloom)"); a level is only set when the person clicks. Vague
verbs suggest nothing.

### Endpoints
- Live: `POST /curriculum-versions/{id}/outcome-checks`, `POST /modules/{id}/outcome-checks`,
  `POST /learning-events/{id}/objective-checks` with `{text, domain, taxonomy_level_id,
  has_parent_links}`. They need `objectives.edit` at the scope that would own the objective
  (the same checks, 404 and 403 as adding one), save nothing, and are limited to 240 per
  minute per user (429 with `Retry-After`; a Redis counter keyed by a hash of the user id).
- Bulk: `GET /curriculum-versions/{id}/objective-checks` returns the findings of every live,
  non-retired objective of the version that the user may see (ADR 027), in curriculum
  order, with the owning module and session and whether the user may edit it. It needs
  `objectives.edit` held somewhere (403 otherwise). It is computed on request, so it always
  reflects the current verb lists and links.

### Not stored
`objectives.detected_verb` and `objectives.quality_flags` stay unused: findings depend on
links and on verb lists that change, so storing them would go stale. A later slice (search,
reports) can fill them from a job if needed.

### Screens
The objective dialog shows the check under the wording after a 600 ms pause: a polite
status line ("Warnings: 1. Notes: 2.") and the list of findings, each with a written
severity and an icon. The version bar offers **Check wording** to people who hold
`objectives.edit`: `/curriculum/versions/:id/quality` lists findings per objective with
severity and rule filters and a link to the item that holds the objective.

## Consequences

- Wording rules can be tuned or translated by editing a JSON file; no migration.
- English rules are heuristics (no part-of-speech tagging): some false alarms and misses are
  expected, which is why findings are advisory.
