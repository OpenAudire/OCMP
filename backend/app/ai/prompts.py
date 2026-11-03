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
    version="1",
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
        "Rules: include every candidate exactly once. coverage is how much of the item the "
        "objective covers: 0 none, 1 up to 20%, 2 up to 40%, 3 up to 60%, 4 up to 80%, 5 up to "
        "100%. depth_match compares the level of the objective's verb with the level the item "
        'expects: "below", "matches", "above", or "not_applicable" when the item states no '
        "depth. confidence is between 0 and 1. For a candidate that is not a match use "
        "is_match false, coverage 0 and an empty evidence_quote. The evidence_quote of a match "
        "must be words copied exactly from the objective."
    ),
)
