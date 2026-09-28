"""Tier 1 deterministic scorers. Runs inside Langfuse as a code evaluator.

Screens for outright breakage only — wrong language, letters from a foreign
script, no list where a list was asked for. Every check restates a rule `src/prompts.py` states as an absolute,
so each is binary; compression is a diagnostic that never gates.

Two constraints on editing this file, both invisible at runtime:

**Write portable Python.** The source is uploaded to Langfuse and executed on
its infrastructure, whose interpreter version is neither controlled nor
observed here. Syntax gated on a recent Python — PEP 758's `except A, B:`, for
one, which a py314-targeted formatter will introduce if a tuple `except` is
written — becomes a SyntaxError there: no scores, and indistinguishable from a
rule that never fired. `install_tier1.py`'s preflight is the only thing that
reports it.

**`Score` and `EvaluationResult` are injected by that runtime** and must not be
defined or imported, which is why every type checker calls them undefined. The
per-line Pyright suppressions are deliberately narrow: a file-level one would
also hide a typo'd local name.
"""

CYRILLIC_FLOOR = 0.70
MIN_BULLETS = 5
BULLET_MARKERS = ("-", "*", "•", "–", "—")
# Letters a Cyrillic summary may legitimately carry: Latin for names and terms
# (with its extensions, for diacritics), Greek for symbols such as μ or Δ, and
# Cyrillic. Anything else — a stray 近 or 复杂 inside Cyrillic prose — is a
# model leaking its training language. The Cyrillic share cannot see it: two
# CJK characters in a 2,000-letter summary move that ratio by 0.1%.
ALLOWED_LETTERS = (
    (0x0041, 0x024F),  # Latin, Latin-1, Extended-A/B
    (0x0370, 0x03FF),  # Greek
    (0x0400, 0x052F),  # Cyrillic and its supplement
    (0x1E00, 0x1EFF),  # Latin Extended Additional
)


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


def _foreign_letters(text):
    return [
        c
        for c in text
        if c.isalpha() and not any(lo <= ord(c) <= hi for lo, hi in ALLOWED_LETTERS)
    ]


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

    foreign = _foreign_letters(output)
    add(
        "t1_script_clean",
        not foreign,
        (
            f"{len(foreign)} letter(s) outside Latin/Greek/Cyrillic: "
            f"{''.join(foreign[:20])}"
            if foreign
            else "No letters outside Latin, Greek and Cyrillic."
        ),
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
