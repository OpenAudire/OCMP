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
