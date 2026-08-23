"""Install `tier1_evaluator.py` into Langfuse as the `tier1-deterministic` evaluator.

POSTing the same evaluator name creates a **new version**, and every evaluation
rule bound to that name follows it automatically — the rule's stored evaluator
id changes to the new version's id, so the rule needs no edit. There is no
separate update route.

Run this after every edit to `tier1_evaluator.py`. It is also the only way to
find out whether the evaluator actually runs: preflight executes the source
against sample data, so a crash comes back here as
`422 evaluator_preflight_failed` with the exception and line number. At runtime
the same crash is silent — the rule stays `active`, the experiment completes,
and no score is ever written.

    uv run python scripts/eval/install_tier1.py
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


def main() -> None:
    """Push the local evaluator source and report the new version."""
    response = requests.post(
        f"{BASE}/api/public/unstable/evaluators",
        auth=AUTH,
        timeout=120,
        json={
            "name": "tier1-deterministic",
            "type": "code",
            "sourceCode": SOURCE.read_text(),
            "sourceCodeLanguage": "PYTHON",
        },
    )
    print(f"POST /unstable/evaluators -> {response.status_code}")
    body = response.json()
    if response.status_code != 200:
        print(json.dumps(body, indent=2)[:2000])
        sys.exit(1)
    print(f"  id={body['id']} version={body['version']}")


if __name__ == "__main__":
    main()
