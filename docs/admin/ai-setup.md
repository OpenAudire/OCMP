# Setting up an AI provider

AI is **off** until you choose a provider, and everything in Curriculum in Context works without it. This is the
step-by-step version; [AI settings](ai.md) explains each setting in full. You need `settings.manage` (platform
admins have it).

!!! warning "Before you start"
    Only curriculum text is ever sent (objective wording, framework items, module and session titles, study-guide
    text), never names or other personal information, and a privacy guard checks every message. If the text is
    processed outside South Africa, that is a transfer abroad your institution must be comfortable with. Read
    [What is sent, and what never is](ai.md#what-is-sent-and-what-never-is) first.

## 1. Give the server its own encryption key (production)

A provider's API key is stored encrypted. On a production install the key is refused until the server has its
own encryption key:

1. `docker compose exec api python -m app.cli new-encryption-key` prints one.
2. Put it in `SECRETS_ENCRYPTION_KEYS` in `.env` and run `docker compose up -d`.
3. Keep it with your backups, together with `SECRET_KEY` ([Encryption keys](ai.md#encryption-keys-and-rotation)).

## 2. Choose where the text may be processed

| If you want | Choose | Notes |
|---|---|---|
| No text to leave your network | **Ollama** (or an **OpenAI-compatible** server you run, for example vLLM) with **On this server or my network** | Turn **local-only mode** on (the default). The address must be on this machine or a private network. |
| A hosted model | **Anthropic Claude**, or **OpenAI-compatible** with the location you are told by the provider | Turn **local-only mode** off, then tick the acknowledgement that curriculum text is processed outside South Africa. |

Local-only mode blocks every other provider whatever its settings say. Choosing a provider that processes text
outside South Africa needs your tick before you can save. Changing the provider, its address or its location
asks you again.

## 3. Fill in the provider

On **Admin > AI settings**:

1. Pick the **provider**.
2. Enter the **model** exactly as the provider writes it (Anthropic's current names are suggested), and the
   **address** if the provider has one (Ollama and OpenAI-compatible servers do).
3. Paste the **API key** if the provider needs one. It is stored encrypted, can never be shown again, and is
   changed by typing a new one.
4. Enter the provider's **prices** per million input and output tokens in US dollars (`0` for a server you run
   yourself). Prices are not built in because they change; without them, calls to an outside provider are refused
   when a cost limit is set.
5. Decide what the guard does on finding personal information: **refuse** (the default) or **replace it with a
   placeholder and send the rest**.
6. Check the **budget** (monthly cost, tokens and calls, calls per run, tokens per answer). The defaults are
   caps, not allowances; leave a box empty for no limit.
7. **Save**.

## 4. Test it

Press **Test connection**. It sends one fixed message ("Reply with the single word: ready") and reports success
with the token counts, or the reason it failed (for example the provider's status code). No curriculum data is
involved. If it fails, the usual causes are a wrong address, a wrong model name, a key that does not match the
provider, or local-only mode blocking an outside provider.

## 5. Try it on the demo, then measure it

1. With the [demo](basics.md) loaded, open **Mapping** and ask for suggestions for one module; review them in the
   [review queue](review-queue.md). Nothing is accepted by itself.
2. Before relying on the AI for real mapping, measure it against people's decisions with a gold set
   ([Checking the AI's mapping](ai-evaluation.md)). The demo's gold set is fictional and shows that the
   machinery works; it says nothing about quality on your curriculum.

## 6. Optional: meaning-based matching

The mapping shortlist, search and near-duplicate checks can use an embeddings server on your own network. It is
separate from the AI provider and optional ([Embeddings](../operations/embeddings.md)).

## Turning it off

Choose **AI off**. The acknowledgement is withdrawn and no feature calls a provider. Past runs stay in the
record (their text is cleared by [retention](basics.md#retention)).
