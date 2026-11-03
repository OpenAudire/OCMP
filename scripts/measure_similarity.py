#!/usr/bin/env python3
"""Measure how well the embeddings model separates near-duplicate objectives (ADR 044).

Usage (from the repository root, with the backend virtual environment, against a running
embeddings server):

    PYTHONPATH=backend backend/.venv/Scripts/python scripts/measure_similarity.py \
        --url http://127.0.0.1:18080 [--out scripts/data/similarity_results.json]

It embeds the fictional pairs in ``scripts/data/similarity_pairs.json`` (English, Afrikaans
and isiXhosa; "same" paraphrases and "different" look-alikes) and the objectives of the demo
programme, through the same adapter the application uses, and prints:

* the similarity of the paraphrases and of the look-alikes per language,
* precision, recall and F1 for each candidate threshold,
* how close the demo objectives are to their nearest neighbour of the same level.

Nothing is written to a database. The pairs are fictional and the Afrikaans and isiXhosa
wording is unreviewed by a native speaker (see the file's ``_comment``).
"""

import argparse
import asyncio
import itertools
import json
import statistics
import sys
from pathlib import Path

from app.ai.embeddings import LocalEmbeddingProvider

ROOT = Path(__file__).resolve().parent.parent
PAIRS = ROOT / "scripts" / "data" / "similarity_pairs.json"
DEMO = ROOT / "backend" / "app" / "demo" / "data" / "bsc-health-sciences-demo.json"
THRESHOLDS = [t / 100 for t in range(70, 100)]


def dot(a: list[float], b: list[float]) -> float:
    # The server returns normalised vectors, so the dot product is the cosine similarity.
    return sum(x * y for x, y in zip(a, b, strict=True))


def spread(values: list[float]) -> dict[str, float]:
    return {
        "n": len(values),
        "min": round(min(values), 4),
        "mean": round(statistics.mean(values), 4),
        "max": round(max(values), 4),
    }


def demo_objectives() -> list[tuple[str, str]]:
    """(level, text) of every objective of the demo programme's current version.

    The ``next_year`` draft is skipped: copy forward gives it identical wording."""
    data = json.loads(DEMO.read_text(encoding="utf-8"))
    found: list[tuple[str, str]] = [("programme", o["text"]) for o in data["programme"]["outcomes"]]
    for module in data["modules"]:
        found.extend(("module", o["text"]) for o in module.get("outcomes", []))
        for event in module.get("events", []):
            found.extend(("learning_event", o["text"]) for o in event.get("objectives", []))
    return found


async def main(url: str, out: Path | None) -> int:
    provider = LocalEmbeddingProvider(url)
    pairs = json.loads(PAIRS.read_text(encoding="utf-8"))["languages"]
    results: dict[str, object] = {}

    scores: dict[str, dict[str, list[float]]] = {}
    for language, groups in pairs.items():
        scores[language] = {}
        for kind in ("same", "different"):
            texts = [t for pair in groups[kind] for t in pair]
            vectors = await provider.embed(texts)
            scores[language][kind] = [
                dot(vectors[i], vectors[i + 1]) for i in range(0, len(vectors), 2)
            ]

    print("== Similarity of the pairs (cosine)")
    summary: dict[str, object] = {}
    for language, kinds in scores.items():
        same, different = spread(kinds["same"]), spread(kinds["different"])
        margin = round(same["min"] - different["max"], 4)
        summary[language] = {"same": same, "different": different, "margin": margin}
        print(
            f"{language}: paraphrases mean {same['mean']:.3f} (min {same['min']:.3f}); "
            f"look-alikes mean {different['mean']:.3f} (max {different['max']:.3f}); "
            f"gap min(same) - max(different) = {margin:+.3f}"
        )
    results["pairs"] = summary

    # Unrelated objectives: every pair among the first sentences of the English paraphrases.
    firsts = [pair[0] for pair in pairs["en"]["same"]]
    vectors = await provider.embed(firsts)
    unrelated = [dot(a, b) for a, b in itertools.combinations(vectors, 2)]
    results["unrelated_english"] = spread(unrelated)
    print(f"unrelated English objectives: {spread(unrelated)}")

    print("\n== Threshold sweep (all languages pooled; per language in the file)")
    print("thr   prec  recall  f1    false+  missed   | recall en/af/xh | false+ en/af/xh")
    sweep = []
    for threshold in THRESHOLDS:
        tp = fp = fn = 0
        per_recall, per_fp = [], []
        for language in pairs:
            same, different = scores[language]["same"], scores[language]["different"]
            hit = sum(s >= threshold for s in same)
            false = sum(d >= threshold for d in different)
            tp, fn, fp = tp + hit, fn + len(same) - hit, fp + false
            per_recall.append(f"{hit}/{len(same)}")
            per_fp.append(f"{false}/{len(different)}")
        precision = tp / (tp + fp) if tp + fp else 1.0
        recall = tp / (tp + fn)
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        sweep.append(
            {
                "threshold": threshold,
                "precision": round(precision, 3),
                "recall": round(recall, 3),
                "f1": round(f1, 3),
                "false_positives": fp,
                "missed": fn,
                "recall_by_language": dict(zip(pairs, per_recall, strict=True)),
                "false_by_language": dict(zip(pairs, per_fp, strict=True)),
            }
        )
        print(
            f"{threshold:.2f}  {precision:.2f}  {recall:.2f}    {f1:.2f}  {fp:>5}  {fn:>6}   "
            f"| {' '.join(per_recall)} | {' '.join(per_fp)}"
        )
    results["sweep"] = sweep

    demo = demo_objectives()
    if demo:
        vectors = await provider.embed([text for _, text in demo])
        nearest = []
        top: list[tuple[float, str, str]] = []
        for i, (level, text) in enumerate(demo):
            others = [
                (dot(vectors[i], vectors[j]), demo[j][1])
                for j in range(len(demo))
                if j != i and demo[j][0] == level
            ]
            if others:
                best = max(others)
                nearest.append(best[0])
                if i < len(demo) and best[0] > 0:
                    top.append((best[0], text, best[1]))
        top.sort(reverse=True)
        ordered = sorted(nearest)
        results["demo"] = {
            "objectives": len(demo),
            **spread(nearest),
            "p90": round(ordered[int(0.9 * (len(ordered) - 1))], 4),
        }
        print(f"\n== Demo objectives ({len(demo)}): nearest same-level neighbour")
        print(results["demo"])
        for score, a, b in top[:6]:
            print(f"  {score:.3f}  {a!r}  <->  {b!r}")

    if out:
        out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nWritten to {out}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default="http://127.0.0.1:18080")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.url, args.out)))
