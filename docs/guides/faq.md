# Frequently asked questions

## Seeing things

**I cannot see a screen in the menu.** The menu shows what your roles allow. Ask your administrator which role
you hold and where ([Users and roles](../admin/users-and-roles.md)).

**A student says they see nothing.** The year must be **published** and the student needs the *Student* role.
Drafts are never shown to students.

**Why does the explorer not show how competencies are mapped?** By default it shows the curriculum's own words
only. An institution can switch on a *Competencies* view that shows, per competency group, where the year builds
it (accepted links only, no scores); see [the explorer](../admin/explorer.md#competencies-optional).

## Editing

**Why can I not edit this?** Only **draft** versions can be edited. A published year is read-only; the programme
director can return it to draft with a written reason.

**The checker says my objective is vague. Must I change it?** No. The wording checker is advice and never blocks
saving. It flags vague verbs, several verbs, a missing domain or upward link, and very long objectives.

**I reworded an approved objective and it is "ready for review" again.** That is intended: a coordinator
approves the new wording.

## Mapping and review

**What does the 0 to 5 coverage mean?** How much of the framework item the objective covers, in steps of 20%.
The **?** button next to the choice explains it with the depth scale.

**The AI suggested a link. Is it counted?** Not until a person accepts it. Reports count accepted links only,
and waiting ones are shown apart.

**Why can I not give the second review?** You cannot second a link you reviewed first or made yourself, and you
need the second-review permission for that module or programme.

**What is the flag "accepted in bulk"?** The link was accepted with many others above a confidence floor. It
counts, but reports show it so a reader knows how it was decided.

**What is "needs a re-check"?** The objective's wording changed after the link was accepted. The link still
counts but is flagged until a reviewer confirms it still fits.

## Reports and numbers

**Which coverage method should I quote?** Quote the method with the figure. Each report prints its method, its
definition and its date; the four methods answer different questions
([Coverage and gap reports](../admin/coverage-reports.md)).

**Are the credit warnings errors?** No, they are advice. A module can differ from credits times hours per credit
by the tolerance (10% by default) before it is flagged.

**The dashboard has no trend lines.** Trends come from a daily snapshot, recorded at 23:55 South African time by
the `scheduler` service. A new installation needs a few days of history.

## AI

**Is my students' information sent to an AI provider?** No. Only curriculum text is sent, and a privacy guard
refuses a message that looks like it holds personal information. Do not type information about students or
patients into objectives or study guides. See [AI settings](../admin/ai.md).

**Can we use Curriculum in Context without AI?** Yes. AI is off until an administrator chooses a provider, and
every feature works without it. [Setting up an AI provider](../admin/ai-setup.md).

**How good are the AI's suggestions?** Measure them against your own experts' mapping before relying on them
([Checking the AI's mapping](../admin/ai-evaluation.md)). The demo's figures are fictional.

## Administration

**How do I try it with fictional data?** `docker compose exec api python -m app.cli load-demo`. Remove it before
real use with `remove-demo` (a dry run unless `--apply`).

**How do I move data between years?** Copy the version forward, or round-trip through Excel
([Exporting](../admin/exporting.md), [Importing](../admin/importing-curriculum.md)).

**Where is the record of who changed something?** The audit log ([Admin basics](../admin/basics.md#audit-log)).
