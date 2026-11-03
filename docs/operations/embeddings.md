# Embeddings (optional)

Embeddings let Curriculum in Context compare the **meaning** of two pieces of wording, not only
their words. In this release they find **near-duplicate objectives** (two objectives of the same
version and level that read almost the same). Meaning-based search and the AI mapping shortlist
use the same service when they arrive (Slices 1.16 and 1.20).

They are **optional and off by default**. With them off, everything else works as before and
the places that would use them say so: the quality check notes that near-duplicate checking is
off, and search and the shortlist use keyword search (full-text) with a notice, never an error.

The decisions behind this page are in ADR 044.

## What runs

| Part | What it is |
|---|---|
| Model | `intfloat/multilingual-e5-small` (MIT licence): 384 numbers per text, up to 512 tokens of input, runs on the CPU. About 470 MB |
| Server | Hugging Face Text Embeddings Inference 1.9.4, CPU image (Apache-2.0 licence), the `embeddings` Compose profile. Pinned by digest in `docker-compose.yml`. The image is about 1 GB |
| Where | Your own server. The address must be on this machine or a private network; a public address is refused. No curriculum text leaves the installation |

**Languages.** The model card lists Afrikaans and isiXhosa (and about 100 languages in all) but
**not isiZulu**. Keyword search works in every language. Quality in low-resource languages is
lower than in English: the model card says so, and the measurements in ADR 044 show the
same. Treat near-duplicate advice in Afrikaans and isiXhosa as a prompt to look, not a verdict.

**What it costs** (measured on a development PC with 8 logical CPUs, 11 GB for Docker):

- Memory: about 2.3 GiB while the model is loaded, idle or busy.
- Speed: about 75 short objectives a second; a 500-objective curriculum takes about 7 seconds.
- First start: the model is downloaded once (about 470 MB; a few minutes on a slow link), then
  kept in the `embeddings_data` volume. A later start takes under 15 seconds.

Plan for at least 3 GB of free memory and 2 GB of disk for the image and the model.

## Turn it on

1. In `.env` set `EMBEDDINGS_LOCAL=true` (the address `EMBEDDINGS_LOCAL_URL` already points at the
   Compose service).
2. Start the service and restart the app so it reads the setting:

   ```bash
   cd deploy
   docker compose --profile embeddings up -d --wait
   docker compose up -d api worker
   ```

3. Check it, and make vectors for what already exists:

   ```bash
   docker compose exec api python -m app.cli embeddings-status
   docker compose exec api python -m app.cli embed-all
   ```

   `embeddings-status` says whether the server answers and how many objectives and framework
   items have a vector. `embed-all` makes the missing ones (safe to repeat; it only does what
   is new or changed) and removes vectors of deleted items.

From then on a saved objective is embedded by a background job within seconds, and its
near-duplicates appear on its card a few seconds after that. Copying a year forward and importing
a framework queue the same work.

## ARM servers

The pinned image is for x86-64. On an ARM server set `OCMP_EMBEDDINGS_IMAGE` in `.env` to the
ARM image (the digest is in `.env.example`). Both images are version 1.9.4.

## A server without internet access

The first start downloads the model from huggingface.co. Where the server cannot reach it, fill the
`embeddings_data` volume somewhere that can, and move it. Both ways below were tried with the
network switched off (a container with no network at all): the volume copy end to end, and the
model folder from the same files.

**Copy the volume** (simplest). On a computer with internet access run the service once
(`docker compose --profile embeddings up -d --wait`) so the model is downloaded, stop it, then:

```bash
docker run --rm -v ocmp_embeddings_data:/data -v "$PWD":/backup alpine \
  tar czf /backup/embeddings_data.tgz -C /data .
```

Copy the file to the server and fill the volume before the first start:

```bash
docker volume create ocmp_embeddings_data
docker run --rm -v ocmp_embeddings_data:/data -v "$PWD":/backup alpine \
  tar xzf /backup/embeddings_data.tgz -C /data
docker compose --profile embeddings up -d --wait
```

With the model already in the volume the server starts without a network (it logs a warning
that it could not look for an optional file, then reports `Ready`).

**Use a model folder.** Put a downloaded copy of the model repository in the volume, for
example `/data/multilingual-e5-small`, and set `EMBEDDINGS_MODEL_ID=/data/multilingual-e5-small`.

The project name in the volume (`ocmp_`) is the Compose project name; `docker volume ls` shows it.

## Changing the model

Do not change `EMBEDDINGS_MODEL_ID` without asking. The vectors of different models cannot be
compared, the column holds 384 numbers, and the near-duplicate threshold was measured for this
model. A change means a new ADR, a new recipe in `app/ai/embeddings.py` (which makes every vector
stale) and a fresh `embed-all`.

## Upgrading the image

The image is pinned by digest so an upgrade is a deliberate change: pick the new version's tag,
read its release notes, replace the digest in `docker-compose.yml` and `.env.example` (both CPU
images), then run `embeddings-status`. Nothing proposes this upgrade automatically: the image is
named inside a variable default, which the dependency bot does not read.

## Troubleshooting

| Sign | Likely cause |
|---|---|
| `embeddings-status` says **unreachable** | The service is not running (`docker compose --profile embeddings ps`), is still downloading the model (watch `docker compose logs embeddings`), or `EMBEDDINGS_LOCAL_URL` is wrong. Near-duplicates and meaning-based matching fall back to keywords meanwhile |
| The service restarts and the log says out of memory | Give Docker more memory (about 3 GB for this service) |
| Objectives are saved but no near-duplicates ever appear | The worker is not running or `EMBEDDINGS_LOCAL` is not `true` for the **worker** too (it reads `.env`). Run `embed-all` once |
| A card shows no pair you expected | The pair is below the threshold (the institution setting `quality.near_duplicate_min_percent`: default 95, lowest 85; changed through `PATCH /api/v1/institution/settings`, there is no screen for it yet), or the objectives are in different versions or at different levels. Only objectives of the same version and level are compared |
| Everything is flagged | The threshold was set low. The model gives unrelated objectives of one subject scores in the high 80s, so values below 90 flag many pairs |

## Privacy

Objective and framework text goes to this server only. The privacy guard's detectors still look
at every text; a text they flag **is embedded anyway** (it never leaves your server and is already
stored) and is listed on the objective quality page so the wording gets fixed. Logs hold
counts only. The vectors are stored in the database and can be rebuilt; they are not exported. See
the [personal data inventory](../privacy/data-inventory.md#embeddings).
