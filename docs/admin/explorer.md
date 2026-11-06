# The curriculum explorer

**Explorer** in the menu lets students, lecturers and external reviewers read the **published** curriculum: what is
taught this week, what a module covers and what each assessment will cover. It is made for a phone first and works
the same on a laptop. Everyone who may read published curriculum sees it, staff included; drafts are only in
**Curriculum**. The design is in [ADR 059](../adr/059-curriculum-explorer.md).

## By week

Choose the curriculum version (only when more than one is published) and the **By week** view. It lists the sessions
of one teaching week across the modules, each with its module, teaching format, the time with the teacher and in
self-study, and what you should be able to do by the end of it. **Earlier** and **Later** step between the weeks that
have sessions. The week you looked at last is remembered in your browser.

There is no calendar yet, so weeks are the **week numbers** the curriculum office put on the sessions. A session
without a week is on its module page under *No week set*.

## Modules

The **Modules** view lists the modules by year or phase. Open one to see:

* **What this module covers**: its outcomes.
* **Sessions, week by week**: each session with its objectives. When you arrive from a search result the session you
  searched for is marked.
* **Assessments**: for each, the method, weight, timing and time, **what it covers** (the outcomes and objectives its
  questions assess, each once) and, opened with *questions or parts*, what each question assesses. This is how a
  student answers "what is in the test".

## Competencies (optional)

When the institution has switched on **Show students where this year builds each competency** (Admin > Institution
settings > Student explorer; off by default, [ADR 061](../adr/061-student-competency-view.md)), a third view,
**Competencies**, lists each competency group of the framework and the modules and sessions of this published year
that build it. It shows where the curriculum teaches a group, not how well, so there are no scores, percentages or
individual framework items. It uses **accepted links only** (suggested, second-review, rejected and re-check links are
not used), published versions only, and only what the student's roles show. Turn it on only when the year's mapping
has been reviewed.

## Search

The **Search the curriculum** button opens [Search](search.md) for the same version. Results open in the explorer for
people who cannot read drafts.

## What it shows and does not show

* Only **published** versions. A module of a draft or archived version is not found.
* Only what your roles let you see: someone with a role in one module sees that module's sessions.
* Retired objectives are left out. The words are the curriculum's own.
* **No framework mappings**, unless the institution switches on the Competencies view above, which shows only competency
  groups, with no scores. The links behind it are working material for the curriculum office and the reports.
* No personal information about students: it shows the same to everyone.

If a student sees nothing, check that the version is **published** (Curriculum, version menu) and that the student has
the *Student* role.
