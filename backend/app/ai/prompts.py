"""Prompt templates owned by the code. Later slices add their versioned prompts here."""

from app.ai.privacy import PromptTemplate

# The connection test: fixed text, no fields, nothing from the database.
CONNECTION_TEST = PromptTemplate(
    name="connection_test",
    version="1",
    system="You check that a connection works. Answer with one short word.",
    user="Reply with the single word: ready",
)


# Mapping an objective to the shortlisted items of a framework (Slice 1.16, ADR 045).
# Bump ``version`` for any change of wording: runs record it and the evaluation harness
# (Slice 1.19) compares versions. The answer is checked by ``app.ai.mapping_answer``.
MAPPING = PromptTemplate(
    name="mapping",
    version="2",
    system=(
        "You help a curriculum committee map learning objectives to the items of a competency "
        "framework. For each candidate item decide whether the objective, as it is worded, "
        "addresses the item, and how much of the item it covers. Judge only from the words you "
        "are given; do not assume what a teacher might do. Answer with JSON only, in the exact "
        "shape requested, and never add a candidate that is not in the list."
    ),
    user=(
        "Framework: {{framework_name}}\n"
        "Objective level: {{objective_level}}\n"
        "Objective: {{objective_text}}\n\n"
        "Candidate framework items (code, then wording):\n{{framework_candidates}}\n\n"
        "{{mapping_examples}}\n"
        'Return JSON of this shape: {"candidates": [{"code": "<a code from the list>", '
        '"is_match": true, "coverage": 3, "depth_match": "matches", "confidence": 0.8, '
        '"rationale": "<one sentence>", "evidence_quote": "<words copied exactly from the '
        'objective>"}]}\n'
        "Rules: list ONLY the candidates the objective matches (is_match true) and leave every "
        'other candidate out; if none match return {"candidates": []}. List each code at most '
        "once. coverage is how much of the item the objective covers: 1 up to 20%, 2 up to 40%, "
        "3 up to 60%, 4 up to 80%, 5 up to 100%. depth_match compares the level of the "
        'objective\'s verb with the level the item expects: "below", "matches" or "above". Use '
        '"not_applicable" only for an item marked [no verb or level]; any other item has a level '
        "to compare. confidence is between 0 and 1. The rationale is one sentence of at most 25 "
        "words. The evidence_quote must be words copied exactly from the objective. Keep the "
        "whole answer short."
    ),
)

# Rewriting an objective so that it can be measured (Slice 1.17, ADR 046). The answer is checked by
# ``app.ai.objective_answers.parse_rewrite``; the person sees a word-by-word comparison and decides.
REWRITE = PromptTemplate(
    name="rewrite",
    version="1",
    system=(
        "You help teachers write learning objectives that can be assessed. Rewrite the objective "
        "so that it starts with one measurable action verb and says what the learner will be able "
        "to do. Keep the meaning, the subject and the language of the original (English, "
        "Afrikaans, isiXhosa or isiZulu). Do not add topics, conditions, numbers or standards "
        "that are not in the original. Answer with JSON only."
    ),
    user=(
        "Objective level: {{objective_level}}\n"
        "Objective: {{objective_text}}\n\n"
        "Problems found by a rule-based checker (may be empty):\n{{quality_findings}}\n\n"
        "Taxonomy levels and the verbs that suggest them:\n{{taxonomy_options}}\n\n"
        'Return JSON of this shape: {"text": "<the rewritten objective>", "rationale": "<one '
        'sentence of at most 25 words saying what you changed and why>"}\n'
        "Rules: at most 600 characters. Prefer a verb from the list above when one fits the "
        "meaning. Use more than one verb only if the objective really has two separate "
        "outcomes. If the objective is already measurable, return it unchanged and say so in "
        "the rationale.{{answer_notes}}"
    ),
)


# Suggesting the domain (knowledge, skill, attitude) and the taxonomy level of an objective
# (Slice 1.17, ADR 046). The levels are offered as short keys (L1, L2, ...) so that the answer
# cannot invent one; ``parse_classification`` checks it.
CLASSIFY = PromptTemplate(
    name="classify",
    version="2",
    system=(
        "You help teachers classify learning objectives. Decide the domain: knowledge (what a "
        "learner knows or understands), skill (what a learner can do) or attitude (values, "
        "professional behaviour). Decide which taxonomy level the objective asks for, judging "
        "from its main verb and what it requires. Answer with JSON only, and use null when you "
        "are not sure."
    ),
    user=(
        "Objective level: {{objective_level}}\n"
        "Objective: {{objective_text}}\n\n"
        "Taxonomy levels (key: name of the scale and level, verbs that suggest it):\n"
        "{{taxonomy_options}}\n\n"
        'Return JSON of this shape: {"domain": "knowledge" | "skill" | "attitude" | null, '
        '"level": "<a key from the list, such as L2>" | null, "confidence": 0.7, '
        '"rationale": "<one sentence of at most 25 words>"}\n'
        "Rules: use only a key from the list. In the rationale name a level by its name, never by "
        "its key. confidence is between 0 and 1 and says how sure you are of both answers "
        "together.{{answer_notes}}"
    ),
)
