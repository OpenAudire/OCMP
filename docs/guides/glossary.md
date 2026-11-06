# Glossary

The words Curriculum in Context uses. Your institution can rename some of the curriculum words (for example
*Module* may read *Course*); the meanings stay the same.

## The curriculum

| Word | Meaning |
|---|---|
| **Programme** | A qualification, for example a BSc. It has one curriculum version per academic year. |
| **Curriculum version** | One academic year of a programme. A **draft** is editable and seen by staff; **published** is read-only and seen by students; **archived** is read-only and hidden from students. |
| **Copy forward** | Making next year's draft from a version, keeping its structure, objectives, tags and mappings. |
| **Phase** | A stage of the programme (a year, a block). |
| **Module** | A course unit with credits and a level. |
| **Session** (learning event) | One teaching activity in a module: a lecture, a skills lab, a clinical placement. Has a format, a week, and contact and self-study time. |
| **Objective** | What a learner should be able to do. **Programme outcomes**, **module outcomes** and **session objectives** are the three levels. |
| **Upward link** | A session objective supporting a module outcome, or a module outcome supporting a programme outcome. It is what makes traceability possible. |
| **Domain** | Knowledge, skills or attitudes (K/S/A). |
| **Taxonomy level / scale** | A level of learning such as *Apply* in Bloom's scale, from the institution's scale. The checker suggests one from the verb. |
| **Assessment** | A test or task of a module with a method, weight and timing; its **items** (questions or parts) are linked to the objectives they assess. |
| **Notional hours** | All the learner's time for a module: contact time, self-study and assessment time. One **credit** stands for a set number of hours (10 by default). |
| **NQF level** | A level of the National Qualifications Framework; the credit check compares credits per level. |
| **Tag list / tag** | An institution's vocabulary (teaching methods, assessment methods, themes) used to label modules, sessions and objectives. A tag can be **inherited** by items below it. |

## Frameworks and mapping

| Word | Meaning |
|---|---|
| **Framework** | A published set of competencies or standards, for example a professional body's core competencies. Loaded from a **framework pack** or an Excel file. |
| **Framework item** | One entry of a framework. A **competency group** is a top-level item with items below it. |
| **Crosswalk** | A recorded relationship between items of two frameworks or two versions of one. |
| **Mapping link** | A connection from an objective to a framework item, with a coverage, a depth and a reason. |
| **Suggested / accepted / rejected** | The state of a link. Only **accepted** links count in reports. A rejected link is kept as an example and not asked about again. |
| **Coverage (0 to 5)** | How much of the framework item the objective covers: 0 none, 1 up to 20%, 2 to 40%, 3 to 60%, 4 to 80%, 5 to 100%. |
| **Depth** | Whether the objective's level is *below*, *matches* or *above* what the item expects, or *not applicable*. |
| **First / second review** | A reviewer's decision on a link. In **four-eyes mode** an accepted link needs a second, different reviewer. |
| **Bulk accept** | Accepting many confident suggestions at once. These links carry a lasting *accepted in bulk* mark in reports. |
| **Accepted by import** | An accepted link that came from an Excel import with no reviewer recorded; flagged in reports. |
| **Needs a re-check** | An accepted link whose objective's wording changed since. It stays accepted but is flagged until a reviewer confirms **Still fits**. |

## Reports

| Word | Meaning |
|---|---|
| **Coverage report** | How well a framework is covered, by one of four labelled methods: **single match**, **multiple match**, **subordinate match** and **weighted content coverage**. Each report prints its method and date. |
| **Gap report** | Framework items with no or low coverage, and objectives with no mapping. |
| **Redundancy** | Items taught in unusually many sessions, and near-duplicate objectives. |
| **Traceability** | The path from a programme outcome through module outcomes and session objectives to framework items. |
| **Heatmap** | Framework groups against phases, shaded by coverage. |
| **Snapshot** | The day's key figures of a version, recorded daily for the dashboard's trend lines. |

## AI and search

| Word | Meaning |
|---|---|
| **AI suggestion** | A link proposed by an AI model. It is always a suggestion, never accepted by the AI. |
| **Privacy guard** | The check that stops personal information leaving the server in a message to an AI provider. |
| **Local-only mode** | Only providers that run on your server or network may be used. On by default. |
| **Embeddings** | Numbers that stand for the meaning of a text, made on your own server, used for meaning-based search and near-duplicate checks. Optional. |
| **Gold set** | A set of mappings made by experts, used to measure how well the AI's suggestions agree with people. |
| **Cohen's kappa** | A measure of agreement between two raters that corrects for chance. 0 is chance, 1 is perfect; the pilot's target is 0.6 or more. |

## Access and records

| Word | Meaning |
|---|---|
| **Role / scope** | A set of permissions given to a person at a place: the institution, a faculty, a programme, a module or a session. A role applies there and below. |
| **Audit log** | The record of who changed what and when, for curriculum, mapping, roles and settings. |
| **API token** | A personal key for scripts; carries its owner's permissions, narrowed to read or write. |
| **Explorer** | The read-only view of published curriculum for students and staff. |
