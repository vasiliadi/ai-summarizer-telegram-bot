"""Tier 1 deterministic scorers for STG-138. Runs inside Langfuse as a code evaluator.

Every check restates a rule that src/prompts.py states as an absolute, so each is
binary. Compression is the exception: it is a diagnostic that sits beside quality
scores, never a gate, because judges reward length and gating would let a model
win by truncating.

Tier 1 screens for outright breakage — wrong language, no list where a list was
asked for. Style and obedience failures are Tier 2/3's job; three checks that
tried to cover them were removed after 150 scored items produced three hits and
no decision (see architecture.md).

**Write portable Python here.** This source is uploaded to Langfuse and executed
on Langfuse's infrastructure, whose interpreter version this project neither
controls nor observes. Syntax gated on a recent Python — PEP 758's
`except A, B:` without parentheses, for one — turns the whole evaluator into a
SyntaxError there, which yields no scores and looks exactly like it never ran.
The repo targets py314, so a formatter will happily introduce that if a tuple
`except` is written.

`Score` and `EvaluationResult` are injected by that runtime and must **not** be
defined or imported here — doing so would ship dead code to the evaluator. The
two names are therefore suppressed per line rather than file-wide: a
file-level `reportUndefinedVariable=false` would also hide a typo'd local
name, and a real error in this module is invisible at runtime, so the editor
is the only place it shows.
"""

CYRILLIC_FLOOR = 0.70
MIN_BULLETS = 5
BULLET_MARKERS = ("-", "*", "•", "–", "—")


def _text(value):
    """Flatten whatever the observation recorded into a plain string."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("content", "text", "output", "value"):
            if key in value:
                return _text(value[key])
        return str(value)
    if isinstance(value, (list, tuple)):
        return "\n".join(_text(v) for v in value)
    return str(value)


def _lines(text):
    return [line.strip() for line in text.splitlines() if line.strip()]


def _is_bullet(line):
    if line.startswith(BULLET_MARKERS):
        return True
    head = line.split(".", 1)[0]
    return head.isdigit() and len(head) <= 2


def _number(value):
    """Coerce a metadata value to a float.

    The experiment runtime hands item metadata to the evaluator with its values
    stringified, so `char_length` arrives as "19845" even though the dataset
    item stores the JSON number 19845. Dividing by it raises TypeError, which
    discards every score built so far — the failure is silent from outside.

    Catches `Exception` rather than `(TypeError, ValueError)` deliberately: a
    tuple `except` is what a py314-targeted formatter rewrites into PEP 758
    syntax, which does not parse on an older interpreter. See the module
    docstring.
    """
    try:
        return float(value)
    except Exception:
        return 0.0


def _cyrillic_ratio(text):
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    cyrillic = sum(1 for c in letters if "Ѐ" <= c <= "ӿ")
    return cyrillic / len(letters)


def evaluate(ctx):
    """Return every applicable Tier 1 score for one generated summary."""
    output = _text(ctx.observation.output)
    item_meta = {}
    if ctx.experiment is not None and ctx.experiment.item_metadata:
        item_meta = ctx.experiment.item_metadata
    obs_meta = ctx.observation.metadata or {}

    # An experiment applies ONE strategy to every item, so the item's own
    # `prompt_key` — the strategy of the trace it was harvested from — is the
    # wrong thing to branch on. The runner passes the strategy it actually used
    # as `run_prompt_key` in the run metadata, which Langfuse merges into the
    # observation metadata. Falling back to the item keeps older runs scoring.
    prompt_key = str(
        obs_meta.get("run_prompt_key") or item_meta.get("prompt_key") or "",
    )
    source_chars = _number(item_meta.get("char_length"))
    lines = _lines(output)

    scores = []
    binary = {}

    def add(name, passed, comment):
        binary[name] = passed
        scores.append(
            Score(name=name, value=passed, data_type="BOOLEAN", comment=comment),  # pyright: ignore[reportUndefinedVariable]
        )

    ratio = _cyrillic_ratio(output)
    add(
        "t1_language_match",
        ratio >= CYRILLIC_FLOOR,
        f"Cyrillic share of letters: {ratio:.2f} (floor {CYRILLIC_FLOOR}).",
    )

    # The bullet guidelines belong to one strategy; scoring the other 0 would
    # penalise it for obeying its own prompt.
    if prompt_key == "key_points_for_transcript":
        bullets = [line for line in lines if _is_bullet(line)]
        add(
            "t1_bullet_count",
            len(bullets) >= MIN_BULLETS,
            f"{len(bullets)} bullets (minimum {MIN_BULLETS}).",
        )

    compression = min(len(output) / source_chars, 1.0) if source_chars else 0.0
    scores.append(
        Score(  # pyright: ignore[reportUndefinedVariable]
            name="t1_compression",
            value=compression,
            data_type="NUMERIC",
            comment=f"{len(output)} output chars / {source_chars:.0f} source chars.",
        ),
    )

    failed = [name for name, ok in binary.items() if not ok]
    scores.append(
        Score(  # pyright: ignore[reportUndefinedVariable]
            name="t1_pass",
            value=not failed,
            data_type="BOOLEAN",
            comment=(
                f"All {len(binary)} applicable checks passed."
                if not failed
                else f"Failed: {', '.join(failed)}."
            ),
        ),
    )

    return EvaluationResult(scores=scores)  # pyright: ignore[reportUndefinedVariable]
