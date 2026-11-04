# Teaching reports

Four reports about how the curriculum is taught and assessed. Open **Reports** in the menu, choose a version
(and a framework where asked). Like every report they state their method and the time they were made, can be
downloaded as Excel or PDF ([Coverage and gap reports](coverage-reports.md#exporting-a-report)), need the
`reports.view` permission and show only what you may see. The design is in
[ADR 053](../adr/053-teaching-reports.md).

## Teaching formats and contact hours

Sessions, contact hours and self-study hours by **teaching format** (the teaching-method tag of the session;
sessions without one are "No format set"), with each format's share of the contact time; the same by phase;
and the hours of each module. The hours are the planned minutes of the sessions.

## Curriculum relationship report

One row for each session and each objective of that session: phase, module, week, session, format, the tags of
the session and of the objective. Meant to be downloaded and filtered in Excel. A session with no objective has
one row with the objective left empty.

## Role balance report (health profile)

Only where the institution has the health profile on (Administration, institution settings); otherwise it is not
listed. Choose a framework. For each phase and each top-level group of the framework: contact hours and share of
the phase's contact time, and the number and share of objectives. A session's time is **divided equally** between
the groups its objectives are accepted for; a session with no accepted link is "Not mapped to this framework".
An objective that maps to two groups counts for both, so those shares can add up to more than 100%.

## Assessment methods

For each value of your assessment-method tag lists: the assessments of that method, the modules that have one,
the objectives their items assess, and the modules and objectives tagged with the method. Below, the objectives
that no assessment item is linked to and that have no assessment-method tag.

## Limits

The words in the tables are English for now. The phase filter exists in the API (`phase_id`) but the screen does
not offer it yet. The figures are plans, not what happened.
