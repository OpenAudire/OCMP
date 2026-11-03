# AI settings

**Admin, then AI settings** (you need `settings.manage`, which platform admins have). Curriculum in
Context works completely without AI, and AI is **off** until you choose a provider. The design is in
[ADR 042](../adr/042-ai-provider-layer-and-privacy-guard.md) and
[ADR 041](../adr/041-encrypted-secrets-at-rest.md).

This slice adds the layer and the screen only. The features that use it (AI mapping suggestions,
objective rewrite, study-guide extraction) arrive in later releases; until then the only thing that
ever calls a provider is the **Test connection** button.

## What is sent, and what never is

Only curriculum text is ever sent to a provider: objective wording, framework item codes and text,
module and session titles and descriptions, study-guide text. Each kind of request is built from a
fixed template, and only those fields can be filled in. A **privacy guard** checks every message
before it leaves the server:

- It looks for email addresses, phone numbers, South African ID numbers, student and staff numbers
  (and long ID-like numbers), IP addresses, titles followed by a name ("Dr Smith", "Mnr Botha",
  "Mnu Dlamini"), hospital, folder and file numbers, dates of birth, and the names of everyone who
  has an account here. The exact rules are listed under [The privacy guard's rules](#the-privacy-guards-rules).
- By default it **refuses**: nothing is sent, and the person is told what kind of information was
  found and where (for example "objective text: 1 email"), never the text itself. The refusal is
  recorded.
- If you choose **Replace it with a placeholder and send the rest**, the found text is swapped for
  a note such as `[email removed]`, checked again, and sent. If anything is still found, the request
  is refused.

!!! warning "The guard helps; it does not make a promise about free text"
    A computer cannot recognise every personal fact. Do not type information about students or
    patients into objectives, descriptions or study guides. See the
    [personal data inventory](../privacy/data-inventory.md).

What is sent is stored exactly as sent with the call (see [retention](basics.md#retention)). Logs
hold only counts and identifiers, never text, answers or keys.

## The privacy guard's rules

The rules are in code (`app/ai/privacy.py`) and tested in both directions: text that must be found and
ordinary curriculum text that must not. They are written to avoid refusing normal teaching material, so
they find personal information that is *written as such* and do not guess.

| What is found | Examples that are found | Examples that are left alone |
|---|---|---|
| Titles with a name, English, Afrikaans, isiZulu | `Dr Smith`, `Prof. Jane Doe`, `Mnr Botha`, `MNU Dlamini`, `Nkk. Zulu`, `Mev. Van der Merwe`, `Me. Botha` | `Give Me Feedback`, `Mnr` alone, `Me Botha` (without the full stop `Me` is the English word), a name that starts with a lowercase letter |
| Hospital, folder and file numbers | `Hospital number: 12345678`, `Folder no 2019/04532`, `MRN 8834221`, `hospitaalnommer 556677`, `inombolo yesibhedlela 556677` | `Case number 12`, `file 20245`, `Hospital 2024 annual report` (a number counts only after a label and with at least five digits) |
| Dates of birth | `DOB: 12/03/1987`, `born 1987-03-12`, `Date of birth: 12 March 1987`, `geboortedatum 12 Maart 1987`, `usuku lokuzalwa 12 Mashi 1987` | `Academic year 2024/2025`, `Week 12`, `due 12 March 2025`, `Sharpeville, 21 March 1960`, `Freud was born in 1856` (a date counts only right after a birth label) |

What the guard reports is the kind and the count, never the text: "objective text: 1 date of birth".

**Be honest about the limits.** Hospital number formats differ from hospital to hospital, so the rule is
deliberately conservative and will miss a short number, or one with no label. A date of birth written
without a label, or with a two-digit year in words, is not found. Names of people who are not users are
found only with a title. These rules cannot replace the instruction not to type personal information
into curriculum fields. Letting an administrator add institution-specific patterns (for example the
exact format of your hospital's folder numbers) is **not built**: it needs a screen, a way to test an
expression safely and a limit on how costly one may be. It is listed as future work.

## Study guides: the patient-information confirmation

A study guide can contain case studies. Whoever uploads one must tick **"This study guide contains no
real patient information"** before it is accepted. The upload screen arrives with the study-guide
extraction (a later release); the confirmation is built now so that it cannot be left out:

- the server refuses an upload without the confirmation for the current version of its text;
- each confirmation is recorded in the [audit log](basics.md#audit-log) as `ai.study_guide_confirmation`
  with who confirmed, when, which version of the text, and a fingerprint (SHA-256) of the file. **The
  file name is not recorded**, because it can contain a person's name;
- the privacy guard refuses to send any study-guide text to a provider unless that confirmation was
  recorded for it.

## Choosing a provider

| Provider | Where the text is processed | Key | Checked against documentation |
|---|---|---|---|
| **AI off** (default) | Nowhere. | none | not needed |
| **Anthropic Claude** | Outside South Africa (fixed). | required | Anthropic's Messages API pages, read 2026-10-27 |
| **OpenAI-compatible** (OpenAI, Azure OpenAI, vLLM and similar) | You say: outside South Africa (default), in South Africa, or on your own network. | optional | Microsoft's and Ollama's descriptions of the API, read 2026-10-27. OpenAI's own reference could not be read, so **run the connection test** before relying on it |
| **Ollama** | You say; the default is your own server or network. | none | Ollama's API page, read 2026-10-27 |

Fill in the **model** (as the provider writes it), the **address** where the provider has one, and the
**API key**. Anthropic's current model names are offered as suggestions in the model field.

### The API key

The key is stored **encrypted** and is **write-only**: once saved it can never be displayed, not even
by you, and not even partly. The screen says only "A key is saved". To change it, type the new one.
To remove it, tick **Remove the saved key** (you cannot remove a key the chosen provider needs). If the
screen says the key "cannot be read", the encryption keys on the server changed; type the key again.
See [Encryption keys](#encryption-keys-and-rotation).

### Prices and cost

Prices change, so none are built in. Enter the provider's current prices per million input and output
tokens in US dollars. The cost of each call is tokens times these prices. If a cost limit is set (see
Budget) and a provider outside your network has no prices, calls are refused with a message saying so;
enter `0` for a server you run yourself.

## Local-only mode and the warning about South Africa

- **Local-only mode** (on by default): only a provider that processes text on this server or your
  network can be chosen or used. Everything else is blocked, whatever the provider's settings say.
- A provider can only be marked **On this server or my network** if its address is `localhost`, a
  private IP address, a name without dots (a Docker service), or ends in `.local`, `.internal` or
  `.lan`. Plain `http://` is only accepted for such addresses.
- Choosing a provider that processes text **outside South Africa** shows a warning that curriculum
  text (not personal information) will be transferred abroad, and you must tick the acknowledgement
  before you can save. The acknowledgement records who and when. If you later change the provider, its
  address or its location, it no longer covers it and you must acknowledge again; until then calls are
  refused.

Which places count as outside South Africa is **your** statement, not something the software works out
from a region name. If you use a cloud region in South Africa, you may mark the provider "In South
Africa"; if unsure, leave it outside.

## Budget

The limits stop AI with a clear message instead of a surprise bill. They count **calendar months in UTC**.
Leave a limit empty for no limit.

| Limit | Default |
|---|---|
| Monthly cost limit (USD) | 10.00 |
| Monthly token limit | 2 000 000 |
| Monthly call limit | 2 000 |
| Most calls in one run | 500 |
| Most tokens in one answer | 1 024 |

The status card shows this month's calls, tokens and cost and says when counting starts again. When a
limit is reached the status turns to **Blocked** and names the limit and the date it resets; raise the
limit to continue earlier. Runs and calls are never deleted (their text is cleared by retention).

## Test connection

The button sends **one fixed message**, "Reply with the single word: ready", through the saved provider.
No curriculum data is involved, it uses a few tokens, it works only when AI is on and the form is saved,
and it can be pressed five times a minute. It reports success with the token counts, or the reason
(for example the provider's status code). Nothing is ever sent unless you press it. The test is
recorded as a run of type "connection test" and in the audit log.

## Encryption keys and rotation

Stored API keys are encrypted with a key from the environment (see
[Configuration](../operations/configuration.md#secrets)).

!!! warning "A production server needs its own `SECRETS_ENCRYPTION_KEYS`"
    With `ENVIRONMENT=production` (the default for a Docker install) a new API key is **refused** until
    `SECRETS_ENCRYPTION_KEYS` is set, and this screen shows a red warning saying so. Settings that need
    no key can still be saved. The server logs a warning each time it starts. Only a development setup
    (`ENVIRONMENT=development`) falls back to a key derived from `SECRET_KEY`.

A key saved earlier with the derived key (before this was required) stays readable. After you set
`SECRETS_ENCRYPTION_KEYS` the screen says "Saved keys use the older encryption key": run
`rotate-secrets` (below) or save each key again.

Keep `SECRET_KEY` **and** `SECRETS_ENCRYPTION_KEYS` with your backups: a restore without the key that
encrypted the stored keys leaves them unreadable and you type them again.

To use a dedicated key, or to change it:

1. `docker compose exec api python -m app.cli new-encryption-key` prints a key.
2. Put it **first** in `SECRETS_ENCRYPTION_KEYS` in `.env` (keep any older key after it, separated by a
   comma), then `docker compose up -d`.
3. `docker compose exec api python -m app.cli rotate-secrets` re-encrypts the stored keys with the newest
   key. It lists any it could not read (it leaves them untouched and exits with an error).
4. When it reports none unread, the old key can be removed.

## What uses AI

| Feature | Where | Notes |
|---|---|---|
| Suggest links to a framework | Mapping page, [AI mapping](mapping.md#suggesting-links-with-ai) | One call per objective that has candidates; suggestions are never accepted automatically |
| Rewrite an objective, suggest its domain and level | The objective dialog, [AI help with the wording](users-and-roles.md#ai-help-with-the-wording) | One call per button press; a suggestion changes nothing until it is used and saved |

The other planned use (reading a study guide) arrives in a later slice. Meaning-based matching in the mapping shortlist uses the optional
[embeddings service](../operations/embeddings.md), which is separate and runs on your own server.

## Who can do what

Only people with `settings.manage` see this screen; the API refuses everyone else. Every change is in the
[audit log](basics.md#audit-log) (`ai.settings_update`); the key itself is recorded only as "changed".
