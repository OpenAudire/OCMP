# ADR 021: Demo Dataset and Framework Pack Import

## Status

Accepted

## Context

The brief (section 7) asks for a fictional demo dataset, "BSc Health Sciences (Demo)" with
3 modules, about 20 learning events, about 60 objectives, a fictional "Demo Graduate
Competencies" framework (8 items in 2 levels), Bloom and Miller scales and tag lists,
loaded with one command. No copyrighted framework text may be shipped.

## Decision

### Framework pack import (`app/services/packs.py`)
- Pydantic models mirror `packs/schema/framework-pack.schema.json` and check what the
  schema cannot: unique item codes, parents that exist, no parent cycles, cross-references
  to known codes, unique level orders and names within a scale.
- `import_pack` creates the framework version, items (parents first), cross-references and
  taxonomy scales through the framework service, so the usual rules and the audit log
  apply. A version already imported is refused; scales with an existing key are reused.
- Phase 1's "import from pack file" builds on this.

### Demo framework
`packs/demo/demo-graduate-competencies.json` was rewritten to match the brief: two groups
(Scholar and Practitioner; Communicator and Professional) with three competencies each,
all text written for OCMP, plus the Bloom (revised) and Miller scales. The loader uses a
copy inside the backend package (the backend image cannot see `packs/`); a test fails if
the two copies differ.

### Demo curriculum
- `app/demo/data/bsc-health-sciences-demo.json`: readable data, validated on load (every
  link and phase reference must resolve). Fictional throughout.
- 6 programme outcomes; 3 modules (year 1, year 2, and one longitudinal module without a
  phase) with 4 outcomes each; 20 sessions with 42 session objectives: 60 objectives, every
  non-programme objective linked upward, all with a domain and a Bloom level.
- 3 tag lists (teaching methods as session formats, assessment methods on modules,
  themes on sessions) and 13 accepted mappings from module outcomes to the framework.
- The version is published for the current academic year.

### Loading
- `python -m app.cli load-demo` loads everything in one transaction through the normal
  services, recorded in the audit log as the `demo.load` operation.
- It uses the institution created by the setup wizard, or creates "OCMP Demo University"
  (health profile on) on a bare install. It reuses the demo framework and tag lists if
  they exist. Loading twice is refused; the second run reports the demo is loaded.

## Consequences

- The demo cannot be removed with a command yet; delete the programme by hand if needed
  (its audit entries remain, by design).
- Phase 1 adds a fictional gold mapping set for the AI evaluation harness on top of this
  data.
