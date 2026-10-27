# ADR 042: AI Provider Layer, Privacy Guard, Budgets and Local-only Mode

## Status

Accepted (Slice 1.14). Builds on ADR 012 (permissions), ADR 016 (AI run and call tables), ADR 017
(audit log) and ADR 041 (encrypted secrets). Brief section 8 (AI subsystem) and section 9 (POPIA).

## Context

Later slices send curriculum text to a language model (mapping, rewriting, study-guide extraction).
The brief's rules: the platform must work without AI; **no personal information may reach a
provider, enforced in code**; admins choose the provider, model, key, budget and may restrict AI to
local providers; a cloud provider outside South Africa needs a warning; every call is recorded.
This slice builds that layer and the admin screen. It builds none of the features that use it.

## Decision

### Providers (`backend/app/ai/providers/`)

`LLMProvider.generate_structured(request: GuardedRequest) -> Completion`. Four adapters:

| Adapter | Used for | Documentation read (2026-10-27) |
|---|---|---|
| `NullProvider` (default) | AI off. No network code at all. | none needed |
| `AnthropicProvider` | Claude, Messages API | `platform.claude.com/docs/en/api/messages`, `get-started`, `api/errors`, `models/overview`: **verified** (endpoint, headers, body, response, usage, error shape, model ids `claude-fable-5-1`, `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5-5`) |
| `OllamaProvider` | a model on the institution's server | `github.com/ollama/ollama/blob/main/docs/api.md`: **verified** (`/api/chat`, `stream: false`, `format`, `options.temperature`, `message.content`, `prompt_eval_count`, `eval_count`); the page gives no error body, so errors are reported by status; `num_predict` is not documented for chat, so no output limit is sent |
| `OpenAICompatibleProvider` | OpenAI, Azure OpenAI, vLLM and similar | **partly verified.** OpenAI's own reference returned 403/404 for every address tried. The chat completions request and response (`/chat/completions`, `messages`, `max_completion_tokens`, `choices[].message.content`, `usage.prompt_tokens/completion_tokens`) were read in Microsoft's Azure OpenAI v1 REST reference, and Ollama's OpenAI compatibility page confirms `/v1/chat/completions` with `max_tokens`. The adapter is built on those two sources and says so in its docstring, the admin guide and the screen. Hosted OpenAI and Azure addresses get `max_completion_tokens`, any other server `max_tokens`. |

Model names are typed by the admin; Anthropic's four documented ids are offered as suggestions
only. Anthropic's `temperature` is sent only when the admin sets one (current models were not
checked for accepting it). Structured output is asked for in the prompt (and in Ollama's `format`),
not with provider features whose current shape was not verified. Embeddings (`EmbeddingProvider`)
arrive with Slice 1.15. vLLM is reached through the OpenAI-compatible adapter.

Adapters never follow redirects (a redirect would carry the key), time out after 60 seconds, and
turn failures into `ProviderError` with the status code and a trimmed provider message with the key
removed.

### The privacy guard (`backend/app/ai/privacy.py`)

Every outbound call is built the same way:

1. A **`PromptTemplate`** owned by the code, with `{{placeholders}}`. Placeholders must be on
   `ALLOWED_FIELDS` (programme/module/event titles and descriptions, objective text, framework item
   code and text, study-guide text, taxonomy and domain names). A template with any other field, or
   a system prompt with a field, cannot be created. The caller must supply exactly the fields the
   template names; any other key is refused. Each field has a maximum length.
2. **Detection** over every field value (and again over the assembled prompt): email addresses;
   phone numbers (international, South African local and separated forms); South African ID numbers
   (13 digits, with or without spaces); "student/staff/employee/passport/ID number" followed by a
   value; any run of 7 to 12 digits and letter-plus-7-to-9-digit codes; IPv4 addresses; a title
   (Dr, Prof, Professor, Mr, Mrs, Ms, Miss, Mx, Mnr, Mev, Adv) followed by a capitalised name; and
   the **display names of every user of the installation** (whole name in either order, any case; a
   single-word name of four or more letters as an exact capitalised word).
3. **Refusal by default** (`on_personal_data = refuse`): the call is not made, a
   `PersonalDataRefusedError` names fields and kinds with counts ("objective_text: 1 email"), never the
   text, and a run with status `failed` and that message is kept. **Redaction** is an admin choice
   (`redact`): findings are replaced by placeholders such as `[email removed]`, the text is scanned
   again, and anything left refuses.
4. The result is a sealed **`GuardedRequest`**. Its constructor refuses to run unless the guard's
   private seal is passed; adapters take only that type. A static test checks that nothing outside
   the gateway builds a provider, and that adapter signatures take only `GuardedRequest`.
5. What is stored with the call (`ai_run_calls.request`) is exactly what was sent.

Limits, stated plainly: pattern detection cannot find every personal fact (a free-text sentence about
a named patient with no title and no matching user), so the screens that will feed this layer must
still say not to type personal information, and the allow-list keeps free text to curriculum fields.
Names of people who are not users are found only with a title. False alarms refuse the call; that is
the safe direction. The patterns are English and South African; other languages need other rules.

### The gateway (`backend/app/services/ai_gateway.py`)

`complete(db, settings, template=, fields=, run_type=, actor_id=, run=None)` is the only door. In order:
AI is on; local-only mode; the outside-South-Africa acknowledgement still covers the provider; the
stored key can be read; the guard; the budget; the provider call; the records. Refusals before the
guard raise `AIRefusedError` subclasses (HTTP 409 if they reach the API); a provider failure raises
`ProviderError` (502). Guard and budget refusals leave a run row (`failed` or `budget_exceeded`) with
counts and reasons. A successful call writes an `ai_runs` row (or joins the caller's run) and an
`ai_run_calls` row with tokens, duration and the response; retention (`purge-ai-content`) clears the
text as before. A new run type, `connection_test`, is added (migration 0019).

**Logs** carry run ids, user ids, provider names, token counts, timings and counts of findings. Never a
prompt, an answer, a name, an address or a key. A test captures the log output of a successful call and
of a refusal and checks this.

### Settings (`ai_settings`, `ai_provider_configs`; `settings.manage`)

| Setting | Default | Why |
|---|---|---|
| Active provider | **Null (AI off)** | The brief: everything works without AI. |
| Local-only mode | **on** | Safest default; turning a cloud provider on is two deliberate steps. |
| When personal data is found | **refuse** | The brief says never send; redaction is opt-in. |
| Monthly cost limit | **USD 10.00** | A cap that cannot surprise; empty means none. |
| Monthly token limit | **2 000 000** | as above |
| Monthly call limit | **2 000** | as above |
| Most calls in one run | **500** | A runaway job stops. |
| Most tokens in one answer | **1 024** | as above |

Prices are **not built in** (they change and could not be tied to a verified source for every
provider): the admin enters USD per million input and output tokens. If a cost limit is set and a
non-local provider has no prices, calls are refused with a message saying so; entering `0` is the way
to say a self-run server costs nothing. Cost is then tokens times price, stored on the run; usage is
the sum over the calendar month (UTC), counted from the run and call tables so it needs no extra table.
A reached limit refuses before sending, says which limit and when it resets, and shows on the screen as
a blocked state.

**Where a provider processes text** is declared per provider: `local` (this server or a private
network), `south_africa` or `outside_south_africa`. Anthropic is fixed at outside South Africa. The
others default to outside South Africa (Ollama to local) and can be changed by the admin. A provider
may only be marked `local` if its address is `localhost`, a loopback or private IP address, a name
without dots or ending `.local`, `.internal` or `.lan`; plain `http://` is only allowed for such
addresses. Which regions count as "outside South Africa" is not decided by the code from a region
name: the admin states it, and anything the code cannot place is treated as outside.

**Local-only mode** refuses a call to any provider whose location is not `local`, and refuses to
save a configuration that chooses one. **The warning**: choosing a provider outside South Africa
needs `acknowledge_outside_south_africa`. The acknowledgement (who, when) is stored with a key made
of provider, address and location, so changing any of them removes the cover and the gateway
refuses until it is given again.

### API (`/api/v1/ai`)

- `GET /settings`, `PATCH /settings`: everything above; keys are write-only.
  A change is made in a savepoint and checked as a whole: a refused change leaves nothing half-saved.
  Audited as `ai.settings_update`.
- `POST /test-connection`: sends the fixed prompt "Reply with the single word: ready" (a template
  with no fields) through the saved, active provider, only when called, at most five times a minute per
  admin (Redis counter keyed by a hash of the user id). It answers 200 with `ok` and a reason code
  either way. Audited as `ai.connection_test`.

### Screen (`frontend/src/admin/AiSettingsPage.tsx`, `/admin/ai`)

Status, provider choice with the chosen provider's fields, the outside-South-Africa warning with its
checkbox, privacy (local-only switch, refuse or redact), budgets with this month's usage, the test
button (disabled when AI is off or the form has unsaved changes), and loading, error, saved and
failed states. The key field is a password field that is always empty; the stored state is a sentence.

## Consequences

- Phase 1 slices 1.16 to 1.18 call `ai_gateway.complete` with their own templates; they cannot add a
  field to a prompt without adding it to `ALLOWED_FIELDS`, which is a reviewed change.
- With a cost limit and no prices a cloud provider is blocked until prices are entered; that is
  intended and the screen says why.
- Whether a managed provider's own retention (for example, no training on API data) is acceptable is
  for the institution's information officer; the screen links to nothing external and says so.
- The earlier `AI_*` environment variables are removed (they were never read).
