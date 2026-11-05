# ADR 059: The Curriculum Explorer

## Status

Accepted (Slice 1.29). Builds on ADR 027 (what a person may see) and ADR 035 (assessments).

## Context

Students and staff need to read the curriculum without the builder: what is taught this week, what a module
covers, and what an assessment will ask. The brief says students see published content only and use a
read-only explorer and search. Phase 1 decision 2 hides session times and venues, so "this week" is by week
number. The mockups have a phone layout for students (390 x 844).

## Decision

**Published versions only, for everyone.** The explorer reads a version only when it is published, for staff
too: drafts belong in the builder. A module or version that is not published, or that the person cannot see,
is a 404. Two reads, `GET /modules/{id}/explorer` and `GET /curriculum-versions/{id}/explorer/week?week=N`
(`services/explorer.py`, `api/v1/explorer.py`), use `visible_version` and `VersionView` (ADR 027), so a person
with a narrow role sees only their modules and sessions.

**The curriculum's own words, never mappings.** The answer holds outcomes, sessions, objectives, tags and
assessments. It holds no framework items or mapping links: those are working material for the curriculum
office and for reports, a student could read an unreviewed or bulk-accepted link as a promise, and the
explorer must not need `curriculum.view`. Retired objectives are left out; objectives still in draft are
shown, as in the search, which uses the same rule.

**"What is covered in this module / assessment".** A module shows what it covers (its outcomes), its sessions
grouped by week with their objectives, and its assessments. An assessment lists, once each and in the module's
order, the objectives its items assess ("what it covers"), and its questions or parts with the objectives each
assesses. This is the data of ADR 035; nothing new is stored.

**"This week" is a week number.** There is no academic calendar. The person steps between the weeks that have
sessions; the week last looked at is remembered in the browser (a convenience, not stored on the server).
Sessions without a week are on the module page under "No week set".

**Phone first.** One column, controls at least 44px tall, no horizontal scrolling, a segmented control to switch
between "By week" and "Modules" (kept in the address), and a search button. Search hits and "where do we teach
this" rows open the explorer for people who cannot read drafts, and the builder for staff who can.

**Menu.** *Explorer* is shown to everyone who may read published curriculum, staff included.

## Not in this slice

* "Where Year 2 builds each competency" for students: it needs mapping links, which the explorer does not show
  (see above). It can be offered later if the institution decides published accepted links may be shown.
* "Upcoming block test" by date: assessments have a free-text timing, not a date.
* Offline use, notifications, and anything personal to the student (their own timetable, marks).

## Consequences

* The explorer needs only `curriculum.view_published`; the existing structure endpoint serves the module list.
* Nothing is cached: each module opens with a handful of queries.
