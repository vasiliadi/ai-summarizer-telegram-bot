"""Rebuild the evaluation dataset from a raw trace harvest.

Screens the harvested generations, classifies each by stratum, applies the
per-stratum quotas, and writes `summarization-compare-v1`.

**Destructive**: it deletes every existing item in the dataset first, so it
refuses to run without `--yes-wipe`.

    uv run python scripts/eval/rebuild_datasets.py --yes-wipe path/to/obs.json

`obs.json` is the raw harvest of traced generations (`langfuse-cli api
observations list --type GENERATION --fields core,io --json`). It is tens of
megabytes and deliberately not tracked; only this script's output is.
"""

import argparse
import collections
import hashlib
import json
import statistics
import sys
import zlib
from pathlib import Path

import _bootstrap
import requests
from langfuse import Langfuse
from tier1_evaluator import CYRILLIC_FLOOR, _cyrillic_ratio

REPO = _bootstrap.load()
BASE, AUTH = _bootstrap.langfuse_rest()

COMPARE = "summarization-compare-v1"

MIN_CHARS = 1500
# Both known-bad transcripts sit at ~0.03; the next real item is 0.14.
MIN_ZLIB_RATIO = 0.10
LONG_CHARS = 8000

COMPARE_QUOTA = {"yt_transcript": 25, "audio_transcript": 20, "web_article": 5}


def content_of(row):
    try:
        parts = json.loads(row["input"])[1]["parts"]
    except Exception:
        return None
    return parts[1]["content"] if len(parts) > 1 else ""


def summary_of(row):
    """The summary the traced generation produced, without its thinking parts."""
    try:
        parts = json.loads(row["output"])[0]["parts"]
    except Exception:
        return ""
    return "\n".join(p["content"] for p in parts if p.get("type") == "text")


def stratum_of(text):
    """Three sources reach `summarize_text`, and no trace field distinguishes them."""
    lines = text.split("\n")
    if len(lines) > 20 and statistics.mean(len(line) for line in lines) < 60:
        return "yt_transcript"  # subtitle format: hard-wrapped ~34-char lines
    if text.lstrip().startswith("<") or "](http" in text[:4000]:
        return "web_article"  # Exa returns HTML, Tavily markdown
    return "audio_transcript"  # WhisperX: segments joined into one blob


def is_degenerate(text):
    return len(zlib.compress(text.encode())) / len(text.encode()) < MIN_ZLIB_RATIO


def load_rows(path):
    """Read the harvested observations out of a langfuse-cli JSON dump."""
    raw = Path(path).read_text()
    return json.loads(raw[raw.index('{"status"') :])["body"]["data"]


def pool(rows):
    seen, out, openings = set(), [], set()
    for row in rows:
        text = content_of(row)
        # Tier 1 scores the Cyrillic share, so keep only traces whose own summary
        # passed that check; a trace without the field would store None.
        if (
            not text
            or not (row.get("metadata") or {}).get("target_language")
            or _cyrillic_ratio(summary_of(row)) < CYRILLIC_FLOOR
        ):
            continue
        digest = hashlib.sha256(text.encode()).hexdigest()[:12]
        if digest in seen:
            continue
        seen.add(digest)
        if len(text) < MIN_CHARS or is_degenerate(text):
            continue
        opening = "".join(text.split())[:120].lower()
        if opening in openings:
            continue
        openings.add(opening)
        out.append((digest, text, row))
    return out


def select(candidates, quota):
    buckets = collections.defaultdict(list)
    for entry in candidates:
        buckets[stratum_of(entry[1])].append(entry)
    picked = []
    for stratum, want in quota.items():
        # Interleave long and short so a stratum's quota is not all one bucket.
        ordered = sorted(buckets[stratum], key=lambda t: t[0])
        longs = [e for e in ordered if len(e[1]) >= LONG_CHARS]
        shorts = [e for e in ordered if len(e[1]) < LONG_CHARS]
        mixed, i = [], 0
        while len(mixed) < want and (longs or shorts):
            src = shorts if (i % 3 == 2 and shorts) else (longs or shorts)
            mixed.append(src.pop(0))
            i += 1
        picked.extend(mixed)
    return picked


def wipe(dataset_name):
    wiped = 0
    while True:
        response = requests.get(
            f"{BASE}/api/public/dataset-items",
            params={"datasetName": dataset_name, "limit": 100},
            auth=AUTH,
            timeout=30,
        )
        response.raise_for_status()
        items = response.json()["data"]
        if not items:
            return wiped
        for item in items:
            requests.delete(
                f"{BASE}/api/public/dataset-items/{item['id']}",
                auth=AUTH,
                timeout=30,
            ).raise_for_status()
        wiped += len(items)


def push(client, dataset_name, picked, prefix):
    for digest, text, row in picked:
        meta = row.get("metadata") or {}
        client.create_dataset_item(
            dataset_name=dataset_name,
            id=f"{prefix}-{digest}",
            input={"content": text, "target_language": meta.get("target_language")},
            metadata={
                "stratum": stratum_of(text),
                "length_bucket": "long" if len(text) >= LONG_CHARS else "short",
                "char_length": len(text),
                "prompt_key": meta.get("prompt_key"),
                "prompt_version": meta.get("prompt_version"),
                "source_model": row.get("model"),
                "source_thinking_level": meta.get("thinking_level"),
            },
            source_trace_id=row["traceId"],
            source_observation_id=row["id"],
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("observations", help="path to the obs.json harvest")
    parser.add_argument(
        "--yes-wipe",
        action="store_true",
        help="required: deletes every item in the dataset before rebuilding",
    )
    args = parser.parse_args()
    if not args.yes_wipe:
        sys.exit("refusing to run: this deletes every item in the dataset")

    rows = load_rows(args.observations)
    client = Langfuse()
    print("wiped", COMPARE, wipe(COMPARE))

    compare = select(pool(rows), COMPARE_QUOTA)
    push(client, COMPARE, compare, "cmp")
    client.flush()
    client.shutdown()

    cells = collections.Counter(
        (stratum_of(t), "long" if len(t) >= LONG_CHARS else "short")
        for _, t, _ in compare
    )
    print(f"\ncompare: {len(compare)} items")
    for cell in sorted(cells):
        print(f"  {cell[0]:18s} {cell[1]:5s} {cells[cell]:3d}")


if __name__ == "__main__":
    main()
