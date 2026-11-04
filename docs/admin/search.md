# Search

Search finds objectives, sessions, modules and framework items in one version of the curriculum, by
their words and (when it is switched on) by their meaning, and answers the question **"Where do we
teach this?"** The design is in [ADR 049](../adr/049-search.md).

## Search the curriculum

Type in the search box at the top of any page (or open **Search** in the menu) and press Enter. The
search runs on the version you are looking at, or the one you last opened; the page lets you choose
another. Results come in groups: **Objectives**, **Sessions**, **Modules** and **Framework items**,
best first, each with where it sits (phase, module, session, week) and **why it matched**:

| Label | Meaning |
|---|---|
| Words | The words of your search are in its text |
| Meaning | Its meaning is close to your search, whether or not it shares words |
| Through an objective | A session or module whose objective matched |

* **Every word has to match**, and the last one may be a beginning: "cardi" finds "cardiac". When
  nothing has all your words, the page says so and shows what has *some* of them.
* **No stemming**: "heart" does not find "cardiac" by words. Meaning does, when it is on.
* You find only what your roles let you see: a module coordinator finds their own module and its
  sessions, a lecturer their own session. Programme outcomes are found only by people who see the
  whole version. Retired and deleted objectives are not searched.
* Framework items are found by people who may read the [framework library](frameworks.md).

### Meaning-based search

It needs the [embeddings service](../operations/embeddings.md) and `embed-all`. Without it the page
says "Meaning-based search is off" (or that the server cannot be reached, or that nothing is embedded
yet) and searches by words only, and everything else keeps working.

### Filters

Open **Filters** to limit a search by phase, module, teaching format, tag, framework, taxonomy level or
domain. A filter that cannot describe a kind of result leaves that kind out, and the page says which:
a domain says nothing about a module, so the sessions and modules are not shown while it is set.
Programme outcomes belong to no module or phase, so those filters leave them out.

The search, the version, the view and the filters are all in the address, so a search can be shared.

## Where do we teach this?

Switch the view to **Where do we teach this?** (or search again with it chosen). The answer is a list
of **sessions in the order they are taught** (phase, module, week, position), each with:

* the objectives that matched;
* **why** the session is listed: its title or description, an objective's words, an objective's meaning,
  or a **framework item** (the question matches a framework item such as "Hand hygiene", and an
  objective taught in this session is *accepted* for that item).

Module outcomes that match are listed apart, under their module, because they are not taught in one
session. Programme outcomes are not listed.

## What happens to what you type

The text of a search is part of the address of the request, so it appears in the server's access log
like any address (it is not stored or logged anywhere else). With meaning-based search on, it is sent
to the embeddings server on your own network, never to an AI provider. Do not search for the names of
people or patients.

## Limits

Searching is limited to 120 searches a minute per person. A search needs two characters and may be up
to 200. The ranking has not been measured on real queries.
