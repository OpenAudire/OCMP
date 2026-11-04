# ADR 049: Search and "Where Do We Teach X?"

## Status

Accepted (Slice 1.20). Builds on ADR 027 (what a user may see of a version), ADR 038 (reading the
framework library), ADR 044 (embeddings, and the full-text fallback with a notice) and ADR 045
(the weights and floors of the mapping shortlist, reused here). Brief, Phase 1 "Search": "Global
search across objectives, events, modules, framework items: keyword (full-text) plus
meaning-based (embeddings), with filters for phase, module, format, tag lists, frameworks,
taxonomy level. 'Where do we teach X?' returns events, objectives and their schedule position."

## Context

People ask two kinds of question of a curriculum: "is there anything about X?" and "where do we
teach X?". The data to answer both exists: wording of objectives, sessions and modules, vectors
of objectives and framework items, tags, formats, and the schedule order. What did not exist is
a way to ask, and the rule that matters most for search: **a result must never reveal curriculum
the user may not see** (ADR 027).

## Decision

### 1. Search is within one version, with the roles' view

`GET /curriculum-versions/{id}/search` searches one version, because "the curriculum" differs by
year and every other reading screen is per version. A version the user cannot see is a 404. Within
it, what is searched is exactly what the roles show: programme outcomes only to people who see
the whole version, a module and its outcomes to people who see the module, a session and its
objectives to people who see the session; a module that is only context for a session is never a
result (its sessions can be). Retired and deleted objectives are not searched. Counts never reveal
hidden curriculum because hidden rows are not in any query's scope.

Framework items are shared by the institution, not part of a version. They are searched for people
who may read the framework library (`curriculum.view` or `frameworks.manage` anywhere, ADR 038).

### 2. Words and meaning

* **Words**: PostgreSQL full-text search with the `simple` configuration (the choice of ADR 044:
  no stemming, the same for English, Afrikaans and isiXhosa). The query is reduced to its words
  (letters and digits only, so nothing in it can be query syntax). Every word must match and the
  last is a prefix ("cardi" finds "cardiac"). When nothing matches every word, results that match
  some of them are shown and the answer says so (`words: "some"`). Single letters are dropped; a
  query needs two characters.
* **Meaning**: when the local embeddings server answers, the query is embedded and compared with
  the stored vectors of objectives (restricted to the objectives the roles show) and framework
  items. Similarity is scaled from a floor of 0.82 to 0.90 (a score of 0 means "not close"; a score
  under 0.1 is dropped). **These are not the mapping shortlist's numbers** (0.75 to 0.95, ADR 045):
  measured on the demo data, the embedding model gives unrelated objectives a cosine of about 0.76
  to 0.80 against a short query (a nonsense query reached 0.81) and good matches 0.85 to 0.92, so
  the shortlist's floor listed every session for every question. The floor belongs to the model
  (`MODEL_KEY`): changing the model means measuring again. Sessions and modules have no vectors: they are found by their
  words and **through their objectives** (a session inherits 0.9 of its best objective's score,
  and the hit says "found through an objective").
* Without embeddings, or when the server is unreachable or nothing is embedded yet, the search
  uses words alone and returns a **notice** saying which (the same three reasons as ADR 044).
  `mode=words` asks for words only.
* The two scores combine as three quarters of the better one plus a quarter of the other, so a
  result both signals support outranks one that only one supports, and two strong signals do not
  both reach a cap and lose their order. These weights are starting values, **not tuned on real
  queries**.

There is no index for the word search: it is a sequential scan of one version's objectives, sessions
and modules, which is fine for thousands of rows. A GIN index is the answer if it is ever slow.

### 3. Filters

Phase, module, teaching format, tag value, framework, taxonomy level and domain. A filter that
cannot describe a kind of result (a taxonomy level says nothing about a module) **leaves that kind
out and the answer names it** (`left_out`) instead of showing unfiltered results. Programme
outcomes have no module or phase, so a phase, module or format filter leaves them out. A framework
filter keeps objectives that have a live, non-rejected link to an item of that framework. A tag
filter keeps what is tagged (inherited tags count, ADR 034).

### 4. "Where do we teach X?"

`GET /curriculum-versions/{id}/where-taught` answers with **sessions in schedule order** (phase,
module, week with no-week sessions last, position), each with the objectives that matched and
why: its own title or description, an objective's words, an objective's meaning, or **the
framework route**: the question matches framework items (the best five), and objectives
*accepted* for those items are taught where they sit ("framework HYG1"). Module outcomes that
match are listed under their module, not under a session. Programme outcomes are not "taught" in
a session and are left out.

### 5. Surfaces

The header search box opens `/search?q=…&version=…` for the version being viewed or last opened.
The page has the filters (collapsed until used or set), the two views (results, where taught) and
the notices, and everything is in the address so a search can be shared. Results link to the
builder (`?item=event:<id>` and `module:<id>`) and to the framework browser. A limit of 120
searches a minute per person (Redis, a hashed user id) stops runaway use.

## What this does not do

* Search across versions or programmes at once.
* Fuzzy matching or spelling correction, stemming, and synonyms ("heart" does not find
  "cardiac" by words; meaning does when embeddings are on).
* Rank by how often a session is taught, or return the schedule dates (the schedule model comes in
  Phase 2: the order is phase, module, week and position).
* Measure the quality of the ranking. Weights and floors are untested on real queries.
* Search the text of study guides or uploaded files (never stored).

## Consequences

* One new endpoint pair and a filter-options endpoint, a header component, a page.
* The visibility rule is in one place (`search._scope`) and the coverage and gap reports reuse it
  (ADR 050), so the same objectives are counted and found.
* The Afrikaans, isiXhosa and isiZulu behaviour of the word search (no stemming) and of meaning
  (a multilingual model) is as in ADR 044 and was not tested here.
