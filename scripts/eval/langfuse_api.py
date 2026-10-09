"""Langfuse v4 read helpers shared by the evaluation scripts.

See evals.md → *Working with the Langfuse API* and *API shapes that cost real time to
rediscover*.
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

    The one decoder; the spec and the live API disagree. See evals.md → *API shapes
    that cost real time to rediscover*.
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
        """GET one path, obeying a 429's retry delay; raises rather than return empty.

        See evals.md → *Working with the Langfuse API*.
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
            # meta.cursor; meta.nextCursor does not exist and would stop at page one.
            cursor = (body.get("meta") or {}).get("cursor")
            if not cursor or not rows:
                return out

    def dataset_id(self, dataset_name: str) -> str:
        """Resolve a dataset name to the id the experiment endpoints require."""
        body = self.get(f"v2/datasets/{quote(dataset_name, safe='')}")
        return body["id"]

    def dataset_size(self, dataset_name: str) -> int:
        """How many items a dataset holds, which a complete run must match."""
        body = self.get("dataset-items", {"datasetName": dataset_name, "limit": 1})
        return body["meta"]["totalItems"]

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
        """List an experiment's items with the requested `fields` groups."""
        return self.paginate(
            "experiment-items",
            {
                "fromStartTime": EPOCH,
                "experimentId": experiment_id,
                "fields": fields,
                "limit": 100,
            },
        )
