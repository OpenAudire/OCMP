"""Prompt templates owned by the code. Later slices add their versioned prompts here."""

from app.ai.privacy import PromptTemplate

# The connection test: fixed text, no fields, nothing from the database.
CONNECTION_TEST = PromptTemplate(
    name="connection_test",
    version="1",
    system="You check that a connection works. Answer with one short word.",
    user="Reply with the single word: ready",
)
