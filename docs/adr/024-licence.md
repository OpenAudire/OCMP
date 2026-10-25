# ADR 024: Licence

## Status

Accepted (2026-10-25, decided by the project owner at Phase 0 approval)

## Context

The brief (section 5) asked the project owner to choose between MIT, Apache-2.0 and
AGPL-3.0, with Apache-2.0 as a placeholder until decided. The placeholder has been in
`LICENSE`, `backend/pyproject.toml`, `frontend/package.json` and the README since the
scaffold (Slice 0.1).

## Decision

OCMP is licensed under the **Apache License 2.0**.

- Permissive, so universities and companies can self-host, adapt and integrate OCMP
  without obligations beyond keeping notices.
- Includes an explicit patent grant and termination clause, which MIT lacks.
- Unlike AGPL-3.0, offering a modified OCMP as a hosted service does not oblige the host
  to publish its changes; the owner accepted this for wider adoption.

The licence text stays in `LICENSE`; package metadata keeps `Apache-2.0`. No `NOTICE` file
is needed until third-party material that requires one is bundled.

## Consequences

- Contributions are accepted under Apache-2.0 (section 5 of the licence), so no separate
  contributor licence agreement is needed.
- Dependencies must have licences compatible with Apache-2.0 (permissive licences, or
  weak copyleft used as separate libraries); GPL/AGPL-only dependencies are not added.
- Framework packs and the demo data are OCMP's own fictional text under the same licence;
  real frameworks are imported by institutions under their own terms and never shipped.
