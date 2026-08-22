"""Langfuse v4 read helpers shared by the evaluation scripts.

Every read here uses a v4 endpoint. The v3 shapes these replaced are deprecated
and Langfuse Cloud stops serving them on 2026-11-16:

  * `GET /datasets/{name}/runs/{runName}` -> `GET /experiments` then
    `GET /experiment-items`. Experiments are queried by dataset **id**, not
    name, so the name has to be resolved through `GET /v2/datasets/{name}`.
  * `GET /traces/{id}` -> `GET /experiment-items?fields=io`. Trace-level
    input/output is deprecated product-wide; an experiment item's `output` is
    the root observation's output, which is what the judge should read anyway.
  * A per-item sweep of `GET /v3/scores` -> `fields=scores` on
    `GET /experiment-items`, which returns each item's scores inline and
    removes the trace join entirely.

`fromStartTime` is **required** on both experiment endpoints, and both paginate
on `meta.cursor`.
"""

from __future__ import annotations

import contextlib
import time
from urllib.parse import quote

import requests

# Experiments predate nothing in this project, so an early floor is a safe
# "everything" bound for the required fromStartTime parameter.
EPOCH = "2020-01-01T00:00:00Z"


def score_value(row: dict) -> object:
    """The comparable value of a score row, chosen by its data type.

    The two types this project reads store their value in opposite places, and
    picking the wrong one fails silently rather than raising:

    * **CATEGORICAL** puts the label in `stringValue` and a numeric category
      mapping in `value` — which is `0` when no score config is linked, as it
      is for every score the judge writes. Reading `value` therefore returns
      `0` for `A`, `B`, `TIE` and `INCONSISTENT` alike, and every comparison
      against a verdict string is false.
    * **BOOLEAN** is the other way round: `value` is the boolean, and
      `stringValue` is the text `"True"`/`"False"` when it is present at all —
      the live v3 API omits it. Preferring `stringValue` here would compare a
      string against a boolean and never match.

    One decoder rather than one per call site, because the two rules diverging
    is exactly how this goes wrong unnoticed.
    """
    if row.get("dataType") == "CATEGORICAL":
        string_value = row.get("stringValue")
        return string_value if string_value is not None else row.get("value")
    return row.get("value")


class LangfuseAPI:
    """Thin, rate-limit-aware reader for the Langfuse public v4 API."""

    def __init__(self, base: str, auth: tuple[str, str]) -> None:
        """Store the host and basic-auth pair used for every request."""
        self.base = base.rstrip("/")
        self.auth = auth

    def get(self, path: str, params: dict | None = None, attempts: int = 8) -> dict:
        """GET one path, honouring the documented rate limit.

        The limit is 30 requests per window and a 429 carries
        `details.retryAfterSeconds`. Obeying that is what makes this terminate —
        blind backoff spends another request per retry. Failing loudly matters
        too: an unchecked 429 falls through as an empty list, which is
        indistinguishable from a model that genuinely scored nothing.
        """
        url = f"{self.base}/api/public/{path.lstrip('/')}"
        for attempt in range(attempts):
            response = requests.get(url, auth=self.auth, timeout=120, params=params)
            if response.status_code == 200:
                return response.json()
            retryable = response.status_code in {429, 500, 502, 503, 504}
            if retryable and attempt < attempts - 1:
                wait = 5.0
                with contextlib.suppress(ValueError, KeyError, TypeError):
                    wait = float(response.json()["details"]["retryAfterSeconds"])
                time.sleep(wait + 1)
                continue
            msg = f"GET {url} -> HTTP {response.status_code}: {response.text[:200]}"
            raise RuntimeError(msg)
        msg = f"GET {url}: giving up after {attempts} attempts"
        raise RuntimeError(msg)

    def paginate(self, path: str, params: dict) -> list:
        """Collect every page of a cursor-paginated v4 list endpoint."""
        out: list = []
        cursor = None
        while True:
            page = dict(params)
            if cursor:
                page["cursor"] = cursor
            body = self.get(path, page)
            rows = body.get("data", [])
            out.extend(rows)
            # meta.cursor, not meta.nextCursor — the latter does not exist and
            # reading it silently truncates the sweep at the first page.
            cursor = (body.get("meta") or {}).get("cursor")
            if not cursor or not rows:
                return out

    def dataset_id(self, dataset_name: str) -> str:
        """Resolve a dataset name to the id the experiment endpoints require."""
        body = self.get(f"v2/datasets/{quote(dataset_name, safe='')}")
        return body["id"]

    def experiments(self, dataset_id: str, name_prefix: str = "") -> list[dict]:
        """List a dataset's experiments, newest first, optionally by name prefix."""
        rows = self.paginate(
            "experiments",
            {"fromStartTime": EPOCH, "datasetId": dataset_id, "limit": 100},
        )
        if name_prefix:
            rows = [r for r in rows if (r.get("name") or "").startswith(name_prefix)]
        return sorted(rows, key=lambda r: r["startTime"], reverse=True)

    def find_experiment(self, dataset_id: str, run_name: str) -> dict | None:
        """Find one experiment by its exact run name."""
        for row in self.experiments(dataset_id):
            if row.get("name") == run_name:
                return row
        return None

    def score_comments(self, score_ids: list[str]) -> dict[str, str]:
        """Map score id -> its comment.

        Scores returned inline by `fields=scores` on an experiment item carry
        the value but not the comment, and the comment is where a Tier 1 score
        records *why* it failed. `fields=core,details` on `GET /v3/scores`
        carries it; the `id` filter takes a comma-separated list.
        """
        out: dict[str, str] = {}
        # Chunked to keep each URL short and each request inside the rate limit.
        for start in range(0, len(score_ids), 50):
            chunk = score_ids[start : start + 50]
            body = self.get(
                "v3/scores",
                {"id": ",".join(chunk), "limit": 100, "fields": "core,details"},
            )
            for row in body.get("data", []):
                out[row["id"]] = row.get("comment") or ""
        return out

    def observations(
        self,
        limit: int = 10,
        obs_type: str = "GENERATION",
        fields: str = "core,io",
        from_start_time: str = EPOCH,
        to_start_time: str | None = None,
    ) -> list[dict]:
        """List observations through the v2 API.

        `GET /observations` (v1) is deprecated in favour of this. Two semantic
        differences bite: v2 returns `input`/`output` as **raw strings** rather
        than parsed JSON, and only the requested `fields` groups are present at
        all — an omitted group is absent, not null.
        """
        params = {
            "type": obs_type,
            "limit": limit,
            "fields": fields,
            "fromStartTime": from_start_time,
        }
        if to_start_time:
            params["toStartTime"] = to_start_time
        return self.get("v2/observations", params).get("data", [])

    def experiment_items(self, experiment_id: str, fields: str) -> list[dict]:
        """List an experiment's items.

        `fields` selects the groups to include: `io` carries input, output and
        expectedOutput; `scores` carries each item's scores inline. Groups that
        are not requested are **absent** from the response rather than null.
        """
        return self.paginate(
            "experiment-items",
            {
                "fromStartTime": EPOCH,
                "experimentId": experiment_id,
                "fields": fields,
                "limit": 100,
            },
        )
