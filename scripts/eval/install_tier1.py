"""Install `tier1_evaluator.py` into Langfuse as a new version of `tier1-on-experiments`.

PATCHes the existing evaluator and never creates one; its preflight is the only place
a crash shows. See evals.md → *A code evaluator receives every metadata value as a
string, and a crash inside it is silent*.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import _bootstrap
import requests

REPO = _bootstrap.load()
BASE, AUTH = _bootstrap.langfuse_rest()

SOURCE = Path(__file__).with_name("tier1_evaluator.py")
NAME = "tier1-on-experiments"


def _evaluator_id() -> str:
    response = requests.get(
        f"{BASE}/api/public/v2/evaluators",
        auth=AUTH,
        timeout=120,
        params={"limit": 100},
    )
    response.raise_for_status()
    matches = [e["id"] for e in response.json()["data"] if e["name"] == NAME]
    if len(matches) != 1:
        sys.exit(f"expected one evaluator named {NAME!r}, found {len(matches)}")
    return matches[0]


def main() -> None:
    """Push the local evaluator source and report the new version."""
    evaluator_id = _evaluator_id()
    response = requests.patch(
        f"{BASE}/api/public/v2/evaluators/{evaluator_id}",
        auth=AUTH,
        timeout=120,
        json={
            "type": "code",
            "sourceCode": SOURCE.read_text(),
            "sourceCodeLanguage": "PYTHON",
        },
    )
    print(f"PATCH /v2/evaluators/{evaluator_id} -> {response.status_code}")
    body = response.json()
    if response.status_code != 200:
        print(json.dumps(body, indent=2)[:2000])
        sys.exit(1)
    print(f"  {body['name']} version={body['version']} status={body['status']}")


if __name__ == "__main__":
    main()
