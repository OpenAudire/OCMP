# ADR 044: Embeddings: Model, Server, Cache and Near-duplicate Detection

## Status

Accepted (Slice 1.15; proposed and approved by the product owner on 2026-11-03, with six
additions that are folded in below). Supersedes the model and serving parts of ADR 007 and
completes the `EmbeddingProvider` promised in ADR 042. Builds on ADR 008 (`vector` extension),
ADR 023 (embeddings profile), ADR 033 (quality checker), ADR 042 (privacy guard) and ADR 043
(`live` filters).

## Context

Slices 1.15 to 1.20 need embeddings: near-duplicate objectives (1.15), the hybrid shortlist for
AI mapping (1.16), meaning-based search (1.20) and redundancy reports (1.23). ADR 007 chose
`paraphrase-multilingual-MiniLM-L12-v2` before its facts were checked. Reading the model's own
pages on 2026-11-03 showed two problems:

- **Afrikaans is not supported.** ADR 007 says "50+ languages including English, Afrikaans". The
  model card's `language:` list and the Sentence Transformers pretrained-models page give 50+
  languages from `ar` to `zh-tw`; neither contains `af`, and neither contains isiZulu or isiXhosa.
  The claim in ADR 007 was an error.
- **Input limit of 128 word pieces** (`max_seq_length: 128`). Objectives fit, but module and
  session descriptions and framework item text can be longer and would be cut silently.

ADR 007 also left the serving approach open ("a simple HTTP API"); no image was ever built
(ADR 023).

Constraints from the brief and CLAUDE.md: the platform works without embeddings; text sent to a
model is curriculum text; local by default; a new data flow updates
`docs/privacy/data-inventory.md`.

## Decision

### 1. Model: `intfloat/multilingual-e5-small`

| | paraphrase-multilingual-MiniLM-L12-v2 (ADR 007) | multilingual-e5-small |
|---|---|---|
| Licence | Apache-2.0 | MIT |
| Dimension | 384 | 384 (the column does not change) |
| Input limit | 128 word pieces | 512 tokens |
| Afrikaans | not listed | listed (`af`) |
| isiXhosa | not listed | listed (`xh`) |
| isiZulu | not listed | **not listed** |
| Prefix | none | `query: ` on every input |

**Verified on the model card on 2026-11-03** (the YAML `language:` list of its README, read with
the `huggingface.co/intfloat/multilingual-e5-small/raw/main/README.md` page): `af` and `xh` are in
the list, `zu` is not. The card also says: 12 layers, embedding size 384, "long texts will be
truncated to at most 512 tokens", the `query: ` prefix is how the model is trained ("otherwise you
will see a performance degradation") and `query: ` is the one to use "for symmetric tasks such as
semantic similarity, bitext mining, paraphrase retrieval", and "low-resource languages may see
performance degradation".

**isiZulu stays unsupported for embeddings**: keyword (full-text) search still works for it, and the
screens that use embeddings fall back to keywords (decision 6).

The prefix is added by our code (`prepared_text`), not by the server's `--default-prompt`, so the
stored `text_hash` is a hash of exactly what the model received. The model key
`intfloat/multilingual-e5-small|query:|v1` names model, prefix and recipe version; changing any of
them makes every vector stale and a sweep replaces them.

### 2. Server: Hugging Face Text Embeddings Inference (CPU), upstream image, pinned by digest

Run `ghcr.io/huggingface/text-embeddings-inference:cpu-1.9` in the optional `embeddings` Compose
profile, pinned by digest, listening on port 8080 (`--port 8080`):

| Fact | Value | How it was checked (2026-11-03) |
|---|---|---|
| Licence | Apache-2.0 | `gh api repos/huggingface/text-embeddings-inference/license` |
| Version | 1.9.4 (latest release; `cpu-1.9` is 1.9.4) | GitHub releases; `GET /info` of the running image |
| x86-64 image | `cpu-1.9`, index digest `sha256:2538ea1c...c78d` | `docker buildx imagetools inspect` |
| **ARM64 image** | **yes: `cpu-arm64-1.9`, index digest `sha256:798cd761...70f1`** | same; a separate tag, so ARM servers set `OCMP_EMBEDDINGS_IMAGE` |
| Size | image about 940 MB, model about 470 MB | `docker image ls`; the model download |
| Health | `GET /health` returns 200 once the model is loaded | the running image |
| Embed | `POST /embed {"inputs": [...], "truncate": true, "normalize": true}` returns a list of 384-number vectors of length 1 | the running image, through our adapter |
| Limits | 512 input tokens, 32 inputs per request (our adapter sends batches of 32) | `GET /info`: `max_input_length`, `max_client_batch_size` |
| Health check tool | `curl` is in the image | `docker exec` |
| Memory, speed | about 2.3 GiB; about 75 short objectives a second on 8 logical CPUs | `docker stats`; a 500-objective timing |

Why this over an image of our own (sentence-transformers and torch behind a small HTTP app):
nothing of ours to build, scan, publish and patch. The cost is a dependency on an upstream project,
and the slice title "embeddings image" becomes "embeddings service". The image is named inside a
Compose variable default, so Dependabot does not propose upgrades: an upgrade is a deliberate edit
(see the operations guide).

**Servers without internet access.** The first start downloads the model from huggingface.co (no
curriculum text is sent). Verified with a container that has no network at all: (a) the same command
starts and reports `Ready` when the model is already in the volume (it logs a warning that an
optional file could not be looked up); (b) `--model-id` can be a folder inside the volume; (c)
the volume can be copied between machines with `tar` and started offline. Documented in
`docs/operations/embeddings.md`. A claim made in the draft of this ADR, that `HF_HUB_OFFLINE` does
this, was not verified and is not used.

### 3. Provider interface

`EmbeddingProvider.embed(texts) -> list[list[float]]` in `app/ai/embeddings.py` with
`NullEmbeddingProvider` (embeddings off; the default) and `LocalEmbeddingProvider`. The adapter
follows no redirects, sends no credentials, checks every vector has 384 numbers and refuses an
address that is not on this machine or a private network (the rule of local AI providers, ADR 042).

**Cloud embeddings are not built in Phase 1** (decision A): a different model has a different
dimension, needs the outside-South-Africa acknowledgement and budget accounting, and must go through
the privacy guard. The unused `EMBEDDINGS_OPENAI*` settings are removed.

### 4. Privacy (owner decision 1)

For the **local** server, a text the privacy guard's detectors flag is **embedded anyway**: it never
leaves the installation and is already stored. It is counted (`flagged`) and never logged. The
bulk quality check lists such objectives as a warning `possible_personal_information`, naming the
**kinds** found (phone number, email address...) and never the values, so the wording gets fixed.
**The guard stays mandatory for any future cloud embedding provider** (it would be a different
adapter behind the AI gateway, ADR 042). The data inventory records all of this.

### 5. Cache: `embeddings` (migration `0022`)

| Column | Notes |
|---|---|
| `entity_type` | `objective` or `framework_item`; VARCHAR + CHECK (`module`, `learning_event` can follow) |
| `entity_id` | UUID, no foreign key (polymorphic); cleaned by the sweep and always joined to the live item |
| `model_key` | see decision 1 |
| `text_hash` | SHA-256 of the prepared text; the item is embedded again only when it changes (spacing alone does not) |
| `vector` | `vector(384)`; HNSW index, cosine, `m = 16`, `ef_construction = 64` |

Unique on (`entity_type`, `entity_id`, `model_key`). Vectors are derived data: not audited, not
exported, rebuilt by `python -m app.cli embed-all` (it only does what is new or changed; the
draft's `--apply` is dropped because nothing is destroyed). Framework items of draft frameworks and
deleted frameworks are not embedded; objectives that are deleted or retired lose their vector.

### 6. When embeddings are off or fail (owner decision 4)

`app/services/retrieval.py` finds framework items for a text: **by meaning** when the server
answers and the chosen frameworks are embedded, otherwise **by keywords** (PostgreSQL full-text
search, `simple` configuration, so there is no stemming that would suit only English: "communicate" does not find "communication", and an English word list would not help Afrikaans, isiXhosa or isiZulu) with a
`notice`: `embeddings_off`, `embeddings_unreachable` or `not_embedded_yet`. It never raises for
these cases. The 1.16 shortlist and the 1.20 search call it; the screens show the notice in words.
The exact searches are scoped by materialised subqueries, not by the vector index, because an index
search that filters afterwards loses results when many closer vectors are in other versions
(copy forward makes identical text in every year).

### 7. Near-duplicate objectives (owner decision 2)

Only objectives of the **same version and level** are compared (copy forward creates identical text
across versions on purpose). A job (`embed_objective`) runs after each create, update and delete
(and a sweep after a copy forward and a framework import): it embeds the objective, then stores its
closest pairs (up to 10, at or above the floor) in `objective_similarities`, replacing the pairs it
was in. Pairs are stored once (smaller id first), so a change to either objective updates the
pair. The result is shown:

- **on the objective card** (the Builder mockup's note: "Near-duplicate of an objective in HSC103,
  Lecture 9 (96% similar). Repeat on purpose, or remove?", with **Compare**), read from
  `GET /curriculum-versions/{id}/near-duplicates` (editors only), and read again six seconds after a
  save because the job takes a moment;
- **in the bulk check** as the `near_duplicate` finding (a note).

A pair is shown only to someone who may see both objectives (ADR 027). The **live check while
typing stays rule-based** (ADR 033): it does not embed unsaved text. While embeddings are off
nothing is reported and the quality page says so.

### 8. The threshold, measured (owner decision 5)

`settings["quality"]["near_duplicate_min_percent"]`: **default 95**, allowed 85 to 100 (the
85 is also the lowest similarity stored, so lowering the threshold never needs a recompute). It was
chosen from `scripts/measure_similarity.py` (repeatable; results in
`scripts/data/similarity_results.json`) on fictional health-sciences objectives: 12 paraphrase pairs
("same") and 12 hard look-alike pairs ("different": same sentence pattern, different topic, for
example the cardiac cycle and the menstrual cycle) in each of English, Afrikaans and isiXhosa, with
the same meaning in all three, plus the 60 objectives of the demo programme. Cosine similarity:

| | Paraphrases: mean (lowest) | Look-alikes: mean (highest) | Lowest paraphrase minus highest look-alike |
|---|---|---|---|
| English | 0.966 (0.939) | 0.905 (0.954) | -0.015 |
| Afrikaans | 0.953 (0.890) | 0.924 (0.969) | -0.080 |
| isiXhosa | 0.962 (0.904) | 0.934 (0.987) | -0.083 |

Unrelated English objectives (66 pairs) scored 0.77 to 0.88 (mean 0.83). The 60 demo objectives,
all genuinely different, have a closest same-level neighbour at 0.86 to 0.94 (mean 0.886, 90th
percentile 0.899); the highest is 0.942 ("Summarise the main functions of each organ system." and
"Identify the main cell organelles and state their functions."), then 0.920 (measuring blood
pressure and comparing a measured pressure with normal ranges).

Threshold sweep, all three languages together (36 paraphrases, 36 look-alikes):

| Threshold | Precision | Recall | F1 | Recall en / af / xh | False alarms en / af / xh |
|---|---|---|---|---|---|
| 0.90 | 0.57 | 0.97 | 0.72 | 12 / 11 / 12 of 12 | 8 / 8 / 10 of 12 |
| 0.93 (best F1) | 0.69 | 0.94 | 0.80 | 12 / 11 / 11 | 2 / 6 / 7 |
| 0.94 | 0.72 | 0.81 | 0.76 | 11 / 9 / 9 | 1 / 5 / 5 |
| **0.95 (chosen)** | **0.75** | **0.75** | **0.75** | **10 / 8 / 9** | **1 / 4 / 4** |
| 0.96 | 0.84 | 0.58 | 0.69 | 8 / 5 / 8 | 0 / 3 / 1 |
| 0.97 | 0.94 | 0.44 | 0.60 | 6 / 3 / 7 | 0 / 0 / 1 |

**Why 95 and not the best F1 of 93:** the closest pair of distinct demo objectives is 94.2%, so 93
would flag two objectives that are not repeats of each other in the data we have, and a noisy note
teaches people to ignore it. 95 reports nothing on the demo. The price is recall: 2 of 12 English
paraphrases, 4 of 12 Afrikaans and 3 of 12 isiXhosa are not caught.

**Languages, compared with English (owner decision 6).** The paraphrases are matched about as well in
the three languages (means 0.953 to 0.966), but the look-alikes score higher in Afrikaans (+0.019)
and isiXhosa (+0.029), so the gap between a repeat and a look-alike shrinks from -0.015 to -0.080
and -0.083. At 95: Afrikaans catches 8 of 12 with 4 false alarms and isiXhosa 9 of 12 with 4, against
10 of 12 with 1 in English. Put plainly, the model matches Afrikaans and isiXhosa by shared words more
than by meaning, so its advice in those languages should be read as a prompt to look, not a verdict.

**Limits of this measurement, stated plainly.** The Afrikaans and isiXhosa sentences were written by
the model that built this slice and **have not been checked by a native speaker**; the isiXhosa in
particular may contain errors. Twelve pairs per language is small, the look-alikes are deliberately
hard, and the demo is 60 objectives of one fictional programme. The numbers are a starting point,
not a validation. They must be redone on real curriculum text and, for retrieval, on the gold set
of Slice 1.19. The setting exists so an institution can move it; the file of pairs is the thing to
extend (and to have a speaker review).

## Consequences

- ADR 007 is marked superseded (its Afrikaans claim was wrong). The model, the prefix, the recipe
  and the threshold belong together: changing the model is a new ADR, a new `MODEL_KEY` and a full
  `embed-all`.
- New table `embeddings` and `objective_similarities` (migration `0022`), new outbound flow (the
  model download), new Redis key (`embeddings:ready`); the data inventory, configuration guide,
  `.env.example`, Compose file, admin guides and CLAUDE.md change in this commit.
- The embeddings service needs about 3 GB of memory and 2 GB of disk; Docker Desktop's default
  memory may need raising.
- Near-duplicates show a few seconds after a save, not at once. If the worker is stopped they do not
  appear until `embed-all` is run.
- Retrieval quality for the AI shortlist (1.16) is not decided by this ADR: 1.16 chooses its own
  prefix and measures it, and a change of prefix is a change of model key.
