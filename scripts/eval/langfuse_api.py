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

    **The OpenAPI spec and the live API disagree here, and the live one wins.**
    The spec declares `CategoricalScore.value` a number (the category mapping)
    with the label in `stringValue`. Observed on `GET /v3/scores`, a categorical
    score arrives as `value: "A"` with `stringValue` absent entirely — verified
    against 25 hand labels. BOOLEAN behaves the same way: `value` is the
    boolean, `stringValue` is absent.

    So `value` carries what is wanted on this route today, and the
    `stringValue` branch is what covers the spec's shape if the API ever starts
    honouring it, or if another route already does — inline scores on
    `GET /experiment-items` return a different envelope. Reading only one field
    fails silently rather than raising: the wrong pick yields `None` or `0` for
    every verdict, which looks exactly like a judge that never ran.

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
