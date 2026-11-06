"""Administration commands.

    python -m app.cli sync-roles
    python -m app.cli create-admin --email admin@example.org --name "Admin"
    python -m app.cli purge-ai-content [--days N]
    python -m app.cli purge-audit-log [--days N]
    python -m app.cli new-encryption-key
    python -m app.cli rotate-secrets
    python -m app.cli setup-token
    python -m app.cli load-demo

``create-admin`` reads the password from OCMP_ADMIN_PASSWORD or prompts for it.
If the account already exists (e.g. created by SSO), it is made a platform
admin without changing its password. This is the bootstrap and recovery path
until the first-run setup wizard exists.

``load-demo`` also makes the demo faculty's curriculum-office account when
OCMP_DEMO_OFFICE_PASSWORD is set (no account, and no password anywhere, otherwise).
"""

import argparse
import asyncio
import getpass
import json
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import MODEL_NAME, get_embedding_provider
from app.ai.errors import AIError, ProviderError
from app.core import database
from app.core.config import get_settings
from app.core.permissions import ScopeType
from app.core.secrets import SecretBox, SecretUnreadableError, new_key
from app.core.security import PasswordPolicyError
from app.demo.loader import load_demo
from app.demo.remover import remove_demo
from app.models import (
    AIProviderConfig,
    AIRun,
    CurriculumVersion,
    EvalRun,
    Framework,
    GoldSet,
    User,
)
from app.models.embedding import EmbeddedType
from app.services import dashboard_metrics, eval_gold, eval_metrics, eval_run, scheduling
from app.services.ai_runs import purge_ai_call_content
from app.services.audit import audit_operation, purge_audit_log
from app.services.authorization import (
    ConflictError,
    InvalidRequestError,
    ScopeRef,
    assign_role,
    get_role,
    sync_system_roles,
)
from app.services.embeddings import coverage, sweep
from app.services.mapping_live import clean_orphan_links
from app.services.retrieval import EmbeddingsState, embeddings_state
from app.services.setup import setup_needed, setup_token
from app.services.users import InvalidEmailError, create_local_user, get_user_by_email

OFFICE_NOTE = (
    "Demo curriculum-office account ready: curriculum.office@example.org "
    "(password from OCMP_DEMO_OFFICE_PASSWORD, role at the demo faculty only)."
)


async def _sync_roles() -> int:
    async with database.session_scope() as db:
        roles = await sync_system_roles(db)
    print(f"System roles synced: {', '.join(r.key for r in roles)}")  # noqa: T201
    return 0


async def _create_admin(email: str, name: str) -> int:
    settings = get_settings()
    async with database.session_scope() as db:
        await sync_system_roles(db)
        role = await get_role(db, key="platform_admin")
        assert role is not None
        user = await get_user_by_email(db, email)
        if user is None:
            password = os.environ.get("OCMP_ADMIN_PASSWORD") or getpass.getpass("Password: ")
            try:
                user = await create_local_user(
                    db, settings, email=email, display_name=name, password=password
                )
            except (InvalidEmailError, PasswordPolicyError) as exc:
                print(f"Error: {exc}", file=sys.stderr)  # noqa: T201
                return 1
        try:
            await assign_role(db, None, user=user, role=role, scope=ScopeRef(ScopeType.INSTANCE))
        except ConflictError:
            print("User is already a platform admin.")  # noqa: T201
            return 0
    print(f"Platform admin ready: {user.id}")  # noqa: T201
    return 0


async def _purge_ai_content(days: int) -> int:
    async with database.session_scope() as db:
        purged = await purge_ai_call_content(db, older_than_days=days)
    print(f"Cleared stored prompts and responses of {purged} AI calls older than {days} days.")  # noqa: T201
    return 0


async def _purge_audit_log(days: int) -> int:
    if days <= 0:
        print("Audit log retention is off (keep forever); nothing deleted.")  # noqa: T201
        return 0
    async with database.session_scope() as db:
        deleted = await purge_audit_log(db, older_than_days=days)
    print(f"Deleted {deleted} audit log entries older than {days} days.")  # noqa: T201
    return 0


async def _remove_demo(apply: bool) -> int:
    async with database.session_scope() as db:
        report = await remove_demo(db, apply=apply)
    if report.nothing and not report.kept:
        print("No demo data found.")  # noqa: T201
        return 0
    heading = "Removed" if apply else "Would remove (add --apply to do it)"
    print(f"{heading}:")  # noqa: T201
    for line in report.removed:
        print(f"  - {line}")  # noqa: T201
    if not report.removed:
        print("  (nothing)")  # noqa: T201
    for line in report.kept:
        print(f"Kept: {line}")  # noqa: T201
    return 0


async def _snapshot_metrics() -> int:
    async with database.session_scope() as db:
        taken = await dashboard_metrics.take_all_snapshots(db)
    print(f"Recorded today's figures for {taken} curriculum versions.")  # noqa: T201
    return 0


async def _run_scheduler() -> int:
    """Record the figures now, then every day at 23:55 in ``TIMEZONE`` (until stopped)."""
    zone = get_settings().timezone
    while True:
        await _snapshot_metrics()
        wait = scheduling.seconds_until_next_run(datetime.now(UTC), zone)
        print(f"Next run in {int(wait)} seconds ({zone}).")  # noqa: T201
        sys.stdout.flush()
        await asyncio.sleep(wait)


async def _clean_orphan_links(apply: bool) -> int:
    async with database.session_scope() as db:
        with audit_operation("mapping.orphan_cleanup", reason="links of deleted objectives"):
            found = await clean_orphan_links(db, apply=apply)
    if apply:
        print(f"Soft-deleted {found} mapping links whose objective was already deleted.")  # noqa: T201
    else:
        print(  # noqa: T201
            f"{found} mapping links belong to deleted objectives. Dry run: nothing changed; "
            "add --apply to soft-delete them."
        )
    return 0


async def _embed_all() -> int:
    """Make the vectors of every objective and framework item that lacks a current one."""
    settings = get_settings()
    if not settings.embeddings_local:
        print(  # noqa: T201
            "Embeddings are off (EMBEDDINGS_LOCAL=false). Start the 'embeddings' profile and "
            "set EMBEDDINGS_LOCAL=true first.",
            file=sys.stderr,
        )
        return 1
    provider = get_embedding_provider(settings)
    try:
        async with database.session_scope() as db:
            for kind in (EmbeddedType.OBJECTIVE, EmbeddedType.FRAMEWORK_ITEM):
                result = await sweep(db, provider, kind)
                print(  # noqa: T201
                    f"{kind.value}: {result.embedded} embedded, {result.unchanged} already "
                    f"current, {result.removed} removed; {result.flagged} of the embedded texts "
                    "hold something the privacy detectors flag (see the quality check)."
                )
    except ProviderError as exc:
        print(f"Error: {exc}", file=sys.stderr)  # noqa: T201
        return 1
    return 0


async def _embeddings_status() -> int:
    settings = get_settings()
    state = await embeddings_state(settings)
    print(f"Embeddings: {state.value} (model {MODEL_NAME})")  # noqa: T201
    async with database.session_scope() as db:
        for item in await coverage(db):
            print(f"  {item.entity_type.value}: {item.embedded} of {item.live} have a vector")  # noqa: T201
    return 0 if state is not EmbeddingsState.UNREACHABLE else 1


async def _load_demo() -> int:
    settings = get_settings()
    password = os.environ.get("OCMP_DEMO_OFFICE_PASSWORD") or None
    try:
        async with database.session_scope() as db:
            summary = await load_demo(db, settings=settings, office_password=password)
            name = summary.programme.name
    except ConflictError as exc:
        print(str(exc))  # noqa: T201
        return 0
    except PasswordPolicyError as exc:
        print(f"Error: {exc}", file=sys.stderr)  # noqa: T201
        return 1
    if summary.draft_only:
        if summary.draft_year:
            print(f"Added the {summary.draft_year} draft to {name}.")  # noqa: T201
        else:
            print(f"Added the missing faculty tag list or account to {name}.")  # noqa: T201
        if summary.office_user_added:
            print(OFFICE_NOTE)  # noqa: T201
        return 0
    print(  # noqa: T201
        f"Loaded {name}: {summary.modules} modules, {summary.learning_events} sessions, "
        f"{summary.objectives} objectives ({summary.objective_links} upward links), "
        f"{summary.framework_items} framework items, {summary.mappings} mappings, "
        f"{summary.tag_lists} tag lists; draft for {summary.draft_year} copied forward."
    )
    if summary.office_user_added:
        print(OFFICE_NOTE)  # noqa: T201
    else:
        print("No curriculum-office demo account made (set OCMP_DEMO_OFFICE_PASSWORD to add one).")  # noqa: T201
    return 0


# --- Evaluation harness (Slice 1.19, ADR 048) -------------------------------------------------


def _percent(value: float | None) -> str:
    return "  n/a" if value is None else f"{value * 100:5.1f}"


def _number(value: float | None) -> str:
    return "  n/a" if value is None else f"{value:5.2f}"


async def _find_framework(db: AsyncSession, name_or_id: str) -> Framework | None:
    try:
        found = await db.get(Framework, uuid.UUID(name_or_id))
        return found if found and not found.is_deleted else None
    except ValueError:
        pass
    rows = list(
        await db.scalars(
            select(Framework).where(Framework.name == name_or_id, Framework.deleted_at.is_(None))
        )
    )
    return rows[0] if len(rows) == 1 else None


async def _find_gold_set(db: AsyncSession, name_or_id: str) -> GoldSet | None:
    try:
        found = await db.get(GoldSet, uuid.UUID(name_or_id))
        return found if found and not found.is_deleted else None
    except ValueError:
        pass
    return await db.scalar(
        select(GoldSet).where(GoldSet.name == name_or_id, GoldSet.deleted_at.is_(None))
    )


def _print_figures(cases: list[eval_metrics.CaseResult], min_coverage: int) -> None:
    print(  # noqa: T201
        "Agreement on which links exist (precision, recall, F1, kappa over links) and on the\n"
        "coverage score (plain and quadratic-weighted kappa, on the links both made):\n"
        "Minimum coverage:  precision recall    F1  kappa  score-kappa  weighted  suggestions"
        "  (right / wrong / missed)"
    )
    for row in eval_metrics.sweep(cases):
        c = row["counts"]
        mark = "  <-" if row["min_coverage"] == min_coverage else ""
        print(  # noqa: T201
            f"  {row['min_coverage']} or more:       {_percent(row['precision'])}%"
            f" {_percent(row['recall'])}% {_number(row['f1'])} {_number(row['kappa'])}"
            f"  {_number(row['coverage_kappa'])} (n={row['coverage_pairs']})"
            f"  {_number(row['coverage_kappa_weighted'])}"
            f"  {row['suggestions']:>6}       ({c['tp']} / {c['fp']} / {c['fn']}){mark}"
        )
    print(  # noqa: T201
        "\nscore-kappa: plain (unweighted) Cohen's kappa between the AI's and the gold set's\n"
        "coverage score (0 to 5) on the links both made; Theurich et al. 2025 report 0.68\n"
        "between their two raters, so this is the comparable figure. weighted: the same with\n"
        "quadratic weights, which forgive near misses (an extra, not comparable). Neither is\n"
        "worked out over which links exist."
    )
    print(f"\nBulk accept at minimum coverage {min_coverage}:")  # noqa: T201
    print("  floor   accepted  right  wrong  precision  left for review")  # noqa: T201
    for row in eval_metrics.bulk_sweep(cases, min_coverage=min_coverage):
        print(  # noqa: T201
            f"  {row['floor']:>4}%  {row['accepted']:>8}  {row['right']:>5}  {row['wrong']:>5}"
            f"  {_percent(row['precision'])}%    {row['left_for_review']:>6}"
        )


async def _eval_template(framework: str | None, out: str) -> int:
    async with database.session_scope() as db:
        chosen = None
        if framework:
            chosen = await _find_framework(db, framework)
            if chosen is None:
                print("Error: no single framework has that name or id.", file=sys.stderr)  # noqa: T201
                return 1
        content = await eval_gold.build_template(db, chosen)
    Path(out).write_bytes(content)
    print(f"Wrote {out}.")  # noqa: T201
    return 0


async def _eval_import(
    file: str | None, name: str | None, framework: str | None, dry_run: bool, demo: bool
) -> int:
    async with database.session_scope() as db:
        if demo:
            path = Path(__file__).parent / "demo" / "data" / "gold-set-demo.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            parsed = eval_gold.read_json(data)
            name = name or data["name"]
            description = data["description"]
            framework = framework or "Demo Graduate Competencies"
        elif file and name and framework:
            description = ""
            parsed = eval_gold.read_workbook(Path(file).read_bytes())
        else:
            print("Error: give FILE, --name and --framework (or --demo).", file=sys.stderr)  # noqa: T201
            return 1
        chosen = await _find_framework(db, framework)
        if chosen is None:
            print("Error: no single framework has that name or id.", file=sys.stderr)  # noqa: T201
            return 1
        await eval_gold.check_codes(db, chosen.id, parsed)
        parsed.problems.sort(key=lambda p: p.row or 0)
        print(  # noqa: T201
            f"{len(parsed.cases)} objectives, {parsed.links} mappings, "
            f"{parsed.empty_cases} objectives that map to nothing."
        )
        for problem in parsed.problems[: eval_gold.MAX_PROBLEMS]:
            where = f"row {problem.row}: " if problem.row else ""
            print(f"  {where}{problem.message}")  # noqa: T201
        if parsed.problems:
            print("Nothing was saved.")  # noqa: T201
            return 1
        if dry_run:
            print("Dry run: nothing was saved.")  # noqa: T201
            return 0
        try:
            await eval_gold.save_gold_set(
                db,
                actor_id=None,
                name=name or "",
                description=description,
                framework=chosen,
                parsed=parsed,
                is_demo=demo,
            )
        except (ConflictError, InvalidRequestError) as exc:
            print(f"Error: {exc}", file=sys.stderr)  # noqa: T201
            return 1
    print(f"Saved the gold set {name!r}.")  # noqa: T201
    return 0


async def _eval_run(gold_set: str, version: str, email: str, top_k: int) -> int:
    settings = get_settings()
    try:
        version_id = uuid.UUID(version)
    except ValueError:
        print("Error: --version must be a curriculum version id.", file=sys.stderr)  # noqa: T201
        return 1
    try:
        embedder = get_embedding_provider(settings)
    except ProviderError:
        embedder = None
    async with database.session_scope() as db:
        gold = await _find_gold_set(db, gold_set)
        chosen = await db.get(CurriculumVersion, version_id)
        user = await db.scalar(select(User).where(User.email == email.casefold()))
        if gold is None or chosen is None or user is None:
            print("Error: gold set, version or user not found.", file=sys.stderr)  # noqa: T201
            return 1
        try:
            evaluation, run = await eval_run.start_eval(
                db, settings, actor_id=user.id, gold_set=gold, version=chosen, top_k=top_k
            )
        except (AIError, ConflictError, InvalidRequestError) as exc:
            print(f"Error: {exc}", file=sys.stderr)  # noqa: T201
            return 1
        await db.commit()
        print(f"Running {run.prompt_version} on {run.model} ({run.total_items} objectives)...")  # noqa: T201
        await eval_run.execute_eval(
            db, settings, evaluation.id, embedder=embedder, after_case=db.commit
        )
        await db.commit()
        await db.refresh(run)
        await db.refresh(evaluation)
        print(  # noqa: T201
            f"Finished: {run.status.value}; {run.done_items} done, {run.failed_items} failed, "
            f"{evaluation.not_found} not found in the version; cost ${run.estimated_cost}."
        )
        if run.error_message:
            print(f"  {run.error_message}")  # noqa: T201
        cases = await eval_run.case_results(db, evaluation)
        print()  # noqa: T201
        _print_figures(cases, 1)
        print(f"\nEvaluation id: {evaluation.id}")  # noqa: T201
    return 0


async def _eval_report(gold_set: str | None, run_id: str | None, min_coverage: int) -> int:
    async with database.session_scope() as db:
        query = select(EvalRun).order_by(EvalRun.created_at)
        if run_id:
            query = query.where(EvalRun.id == uuid.UUID(run_id))
        elif gold_set:
            gold = await _find_gold_set(db, gold_set)
            if gold is None:
                print("Error: gold set not found.", file=sys.stderr)  # noqa: T201
                return 1
            query = query.where(EvalRun.gold_set_id == gold.id)
        evaluations = list(await db.scalars(query))
        if not evaluations:
            print("No evaluation runs.")  # noqa: T201
            return 0
        print(  # noqa: T201
            f"Figures at minimum coverage {min_coverage}, most specific item preferred.\n"
            "Prompt        Model                          objectives  precision recall   F1  "
            "kappa   cost"
        )
        for evaluation in evaluations:
            run = await db.get(AIRun, evaluation.ai_run_id)
            if run is None:
                continue
            cases = await eval_run.case_results(db, evaluation)
            scores = eval_metrics.score(cases, min_coverage=min_coverage)
            print(  # noqa: T201
                f"{run.prompt_version:<13} {run.model:<30} {scores.objectives:>10}"
                f"  {_percent(scores.precision)}% {_percent(scores.recall)}%"
                f" {_number(scores.f1)} {_number(scores.kappa)}  ${run.estimated_cost}"
            )
        if len(evaluations) == 1 or run_id:
            print()  # noqa: T201
            _print_figures(await eval_run.case_results(db, evaluations[-1]), min_coverage)
    return 0


def _new_encryption_key() -> int:
    print(new_key())  # noqa: T201
    return 0


async def _rotate_secrets() -> int:
    """Re-encrypt every stored secret with the newest key in SECRETS_ENCRYPTION_KEYS."""
    box = SecretBox.from_settings(get_settings())
    if not box.may_encrypt:
        print(  # noqa: T201
            "SECRETS_ENCRYPTION_KEYS is not set (production). Set it first: make a key with "
            "'python -m app.cli new-encryption-key', then run this command again.",
            file=sys.stderr,
        )
        return 1
    rotated = unchanged = unreadable = 0
    with audit_operation("secrets.rotate"):
        async with database.session_scope() as db:
            configs = await db.scalars(
                select(AIProviderConfig).where(AIProviderConfig.api_key_encrypted.is_not(None))
            )
            for config in configs:
                stored = config.api_key_encrypted
                assert stored is not None
                if not box.needs_rotation(stored):
                    unchanged += 1
                    continue
                try:
                    config.api_key_encrypted = box.encrypt(box.decrypt(stored))
                except SecretUnreadableError:
                    unreadable += 1
                    continue
                rotated += 1
    print(f"Re-encrypted {rotated} secrets; {unchanged} already used the newest key.")  # noqa: T201
    if unreadable:
        print(  # noqa: T201
            f"{unreadable} secrets could not be read with the configured keys and were left "
            "as they are. Add the key that encrypted them to SECRETS_ENCRYPTION_KEYS, or "
            "enter them again in Admin > AI settings.",
            file=sys.stderr,
        )
        return 1
    return 0


async def _setup_token() -> int:
    async with database.session_scope() as db:
        pending = await setup_needed(db)
    if not pending:
        print("Setup is already complete; the setup token is no longer accepted.")  # noqa: T201
        return 0
    print(f"Setup token: {setup_token(get_settings())}")  # noqa: T201
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("sync-roles", help="Create or update the built-in roles.")
    admin = commands.add_parser("create-admin", help="Create or promote a platform admin.")
    admin.add_argument("--email", required=True)
    admin.add_argument("--name", default="Platform admin")
    purge = commands.add_parser(
        "purge-ai-content", help="Clear stored AI prompts and responses past retention."
    )
    purge.add_argument("--days", type=int, default=None, help="Default: AI_CALL_RETENTION_DAYS.")
    commands.add_parser(
        "new-encryption-key", help="Make a key for SECRETS_ENCRYPTION_KEYS (printed once)."
    )
    commands.add_parser(
        "rotate-secrets", help="Re-encrypt stored secrets with the newest encryption key."
    )
    commands.add_parser(
        "embed-all", help="Make the embeddings of objectives and framework items that lack one."
    )
    commands.add_parser(
        "embeddings-status", help="Show whether the embeddings server answers and what is embedded."
    )
    template = commands.add_parser(
        "eval-template", help="Write the empty Excel gold-set template (Slice 1.19)."
    )
    template.add_argument("--framework", default=None, help="Name or id: lists its item codes.")
    template.add_argument("--out", default="gold-set-template.xlsx")
    gold_import = commands.add_parser(
        "eval-import", help="Import a filled-in gold-set workbook (or --demo)."
    )
    gold_import.add_argument("file", nargs="?", default=None)
    gold_import.add_argument("--name", default=None)
    gold_import.add_argument("--framework", default=None, help="Name or id.")
    gold_import.add_argument("--dry-run", action="store_true", help="Check only.")
    gold_import.add_argument("--demo", action="store_true", help="The fictional demo gold set.")
    evaluate = commands.add_parser(
        "eval-run", help="Ask the AI to map a gold set's objectives and report the figures."
    )
    evaluate.add_argument("--gold-set", required=True, help="Name or id.")
    evaluate.add_argument("--version", required=True, help="Curriculum version id.")
    evaluate.add_argument("--email", required=True, help="The person the run is made for.")
    evaluate.add_argument("--top-k", type=int, default=10)
    report = commands.add_parser("eval-report", help="Figures of evaluation runs.")
    report.add_argument("--gold-set", default=None, help="Name or id.")
    report.add_argument("--run", default=None, help="Evaluation id.")
    report.add_argument("--min-coverage", type=int, default=1)
    demo_removal = commands.add_parser(
        "remove-demo",
        help="Remove the fictional demo data (dry run unless --apply).",
    )
    demo_removal.add_argument("--apply", action="store_true", help="Make the change.")
    commands.add_parser(
        "snapshot-metrics",
        help="Record today's key figures of every draft and published version (run it nightly).",
    )
    commands.add_parser(
        "run-scheduler",
        help="Run snapshot-metrics now and then every day at 23:55 in TIMEZONE (keeps running).",
    )
    commands.add_parser("setup-token", help="Show the first-run setup token.")
    commands.add_parser("load-demo", help="Load the fictional BSc Health Sciences (Demo) data.")
    orphans = commands.add_parser(
        "clean-orphan-links",
        help="Soft-delete mapping links whose objective was deleted (dry run unless --apply).",
    )
    orphans.add_argument("--apply", action="store_true", help="Make the change.")
    audit_purge = commands.add_parser(
        "purge-audit-log", help="Delete audit log entries past retention."
    )
    audit_purge.add_argument(
        "--days", type=int, default=None, help="Default: AUDIT_LOG_RETENTION_DAYS."
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    database.init_database(settings)

    async def run() -> int:
        try:
            if args.command == "sync-roles":
                return await _sync_roles()
            if args.command == "clean-orphan-links":
                return await _clean_orphan_links(args.apply)
            if args.command == "remove-demo":
                return await _remove_demo(args.apply)
            if args.command == "snapshot-metrics":
                return await _snapshot_metrics()
            if args.command == "run-scheduler":
                return await _run_scheduler()
            if args.command == "embed-all":
                return await _embed_all()
            if args.command == "embeddings-status":
                return await _embeddings_status()
            if args.command == "load-demo":
                return await _load_demo()
            if args.command == "eval-template":
                return await _eval_template(args.framework, args.out)
            if args.command == "eval-import":
                return await _eval_import(
                    args.file, args.name, args.framework, args.dry_run, args.demo
                )
            if args.command == "eval-run":
                return await _eval_run(args.gold_set, args.version, args.email, args.top_k)
            if args.command == "eval-report":
                return await _eval_report(args.gold_set, args.run, args.min_coverage)
            if args.command == "new-encryption-key":
                return _new_encryption_key()
            if args.command == "rotate-secrets":
                return await _rotate_secrets()
            if args.command == "setup-token":
                return await _setup_token()
            if args.command == "purge-audit-log":
                days = args.days if args.days is not None else settings.audit_log_retention_days
                return await _purge_audit_log(days)
            if args.command == "purge-ai-content":
                days = args.days if args.days is not None else settings.ai_call_retention_days
                return await _purge_ai_content(days)
            return await _create_admin(args.email, args.name)
        finally:
            await database.close_database()

    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())
