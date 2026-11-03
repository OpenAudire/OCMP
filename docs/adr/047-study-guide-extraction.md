# ADR 047: Study-guide Extraction

## Status

Accepted (Slice 1.18). Builds on ADR 042 (privacy guard and the study-guide confirmation),
ADR 045 (the run, progress and answer-checking approach) and ADR 046 (single-call helpers).
Brief section 8, "Other AI tasks": "Extract objectives from uploaded PDF/DOCX study guides into
draft objectives for review".

## Context

Many modules already have their learning outcomes written in a study guide. Typing them in again
is slow and error-prone. A study guide is the riskiest text the platform sends to an AI service:
it is long, written by lecturers, and can contain case studies. ADR 042 therefore made two
rules that this slice must keep: the uploader confirms that the guide holds no real patient
information, and the privacy guard refuses study-guide text without the receipt of that
confirmation.

## Decision

### Flow

1. **Upload** (`POST /modules/{id}/study-guides`, multipart: `file`, `confirmed`,
   `text_version`). Needs `objectives.edit` and `ai.run` at the module, on a draft version.
   The order is fixed: AI must be ready (so nothing is recorded for an impossible run), then
   the **confirmation is recorded** (`confirm_no_patient_information`, which writes the audit
   event with the user, the time, the text version, the file's SHA-256 and its size), and only
   then is the file read. A missing, unticked or stale confirmation is `422` and nothing is read,
   recorded or queued.
2. **The file is read in the request and never stored.** Its kind comes from its first bytes (a
   PDF, or a zip that holds `word/document.xml`), not from its name. **The file name is never
   read, stored or logged**: it can carry a person's name or a patient reference. Limits are
   checked before anything is unpacked: 10 MB, 200 PDF pages, 60 MB unpacked and 2 000 files in
   a Word file, 400 000 characters of text. Password-protected PDFs, damaged files and files
   with almost no text (scans: there is no OCR) are refused with a reason. Readers: `pypdf`
   (BSD-3-Clause) and `python-docx` (MIT); both read in memory.
3. The text is cut at line ends into **pieces of about 12 000 characters, at most 8** (the guard
   allows 60 000 per field). If the guide is longer, the end is left out and the run says so. The
   pieces are kept in Redis for **one hour** under the run's id and deleted when the run ends.
4. A **run** (`ai_runs`, type `extraction`, prompt `extract:1`) is queued; a background job
   (`run_study_guide`, no automatic retries, commits after every piece) makes **one guarded call
   per piece** and saves what it finds as *proposals*. Progress is `done_items` of `total_items`
   pieces. One reading per module at a time; a run that stops without progress is ended by the same
   rule as mapping runs (ADR 045).
5. **A person decides each proposal** on the module page: edit the wording or domain, then
   *Accept* (an ordinary draft objective of the module through the objective service, with its
   own audit entry `curriculum.objective_create`, "from a study guide proposal") or *Reject*.
   **Nothing becomes curriculum on its own**, and accepted objectives are drafts (approval needs
   `objectives.approve`, as always).

### The receipt in a background job

The privacy guard needs a `ConfirmationReceipt`, which only the confirmation service can make and
which cannot be passed to a job. The job asks the same service for it again
(`recorded_receipt`): it exists only if **this person's confirmation of this document (its hash)
for the current text version is in the audit log**. Nothing is recorded by asking. Without it the
run fails and nothing is sent.

### What is sent and what is kept

| What | Where | How long |
|---|---|---|
| The pieces of the guide's text | Redis `study-guide:<run id>` | 1 hour, deleted when the run ends |
| The same text inside each prompt, and the answer | `ai_run_calls.request` and `response` | `AI_CALL_RETENTION_DAYS`, as every call (ADR 042) |
| The module's title and the text of one piece per call | sent to the AI service | not kept by the platform beyond the above |
| Proposed wording and a quote of at most 400 characters | `objective_proposals` | until decided; kept after (a decision is not undone) |
| The confirmation (user, time, text version, file hash and size) | audit log | as the audit log |
| The file, and its name | **nowhere** | |

### Checking the answer (`ai/extraction_answer.py`)

The answer is untrusted text. It must be JSON with an `objectives` list (none is a valid answer).
Each objective needs wording (at most 600 characters), a `source_quote` that is **words of the piece
that was sent** (at most 400 characters), and a domain or `null`. **Wording may not contain a number
that is not in its quote**, so a made-up "80%" cannot enter the curriculum. Wording the module already
has, or has ever had proposed (rejected proposals included), is skipped. An unusable answer is retried once with
fixed phrases that never repeat the model's words; a second failure counts as a failed piece. A piece
whose text the guard refuses (personal information) is skipped and counted, and the run goes on.

## Consequences

- Only **module outcomes** are proposed. Session objectives are not extracted (a guide rarely ties
  them to the module's sessions in a way that can be checked), and upward links, taxonomy levels
  and mappings are left to the people accepting them (the AI help of ADR 046 can suggest a level).
- The quote proves that the wording is based on the guide, not that it is the right outcome; a
  person reads each one.
- Text recognition is not built, so a scanned guide cannot be used. A very long guide is read only
  in its first part (about 96 000 characters).
- The proxy (`deploy/Caddyfile`) refuses an upload body over 11 MB for this route before it is received,
  so an oversized file is not written to disk first; the API checks 10 MB itself.
- Two readers parse untrusted files in the API process. They are pure Python, run on bounded
  input, and the size checks come first; a hostile file can still make a request slow or fail it
  with a reason, but not write anything.
- Rejected wording is kept, so reading the same guide again does not put it to the reviewer a
  second time (a rejection is a person's "no", as in mapping, ADR 045).
- The Playwright check covers the panel and the upload dialog with AI off; a real reading needs a
  provider key and was not run in CI.
