# ADR 007: Embedding Model

## Status

**Superseded by [ADR 044](044-embeddings-model-server-and-cache.md)** (Slice 1.15, 2026-11-03), which
replaces the model, the serving approach and the dimension notes below.

**Correction.** This ADR said the model supports "50+ languages including English, Afrikaans". That
was an error: the model card's language list and the Sentence Transformers documentation do not
include Afrikaans (or isiZulu or isiXhosa). The 128-token input limit it states is also too short
for descriptions. ADR 044 chooses `intfloat/multilingual-e5-small`, whose card lists Afrikaans and
isiXhosa but not isiZulu. The text below is kept as it was for the record.

## Context

OCMP uses embeddings for:
- Semantic search across objectives and framework items
- Finding similar objectives (duplicate detection)
- Candidate shortlisting for AI mapping
- "Where do we teach X?" queries

We need an embedding model that:
- Runs locally (privacy, no API costs for basic operations)
- Supports multiple languages (South African context)
- Performs well on academic/medical text
- Fits in reasonable memory (~2GB)

## Decision

Use **sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2** as the default local embedding model.

### Specifications

- **Dimensions**: 384
- **Languages**: 50+ languages including English, Afrikaans
- **Model size**: ~470MB
- **Sequence length**: 128 tokens
- **Performance**: Good balance of quality and speed

### Deployment

- Optional `embeddings` container in Docker Compose
- Uses sentence-transformers with a simple HTTP API
- Configurable to use external provider (OpenAI, etc.) instead

### Alternative configurations

| Use case | Model |
|----------|-------|
| Local, multilingual (default) | paraphrase-multilingual-MiniLM-L12-v2 |
| Local, English-only, higher quality | all-MiniLM-L6-v2 |
| Cloud, highest quality | text-embedding-3-small (OpenAI) |

## Rationale

1. **Multilingual**: Required for South African institutions
2. **Local**: Privacy-preserving, no per-request costs
3. **Small**: Runs on CPU in constrained environments
4. **Proven**: Widely used, well-tested model

## Consequences

- Embedding dimension is 384 (pgvector column)
- Re-embed if model changes (tracked by model name in Embedding table)
- Initial embedding of a large curriculum takes time (batch processing)
- GPU optional but recommended for large institutions
