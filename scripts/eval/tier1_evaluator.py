"""Tier 1 deterministic scorers for STG-138. Runs inside Langfuse as a code evaluator.

Every check restates a rule that src/prompts.py states as an absolute, so each is
binary. Compression is the exception: it is a diagnostic that sits beside quality
scores, never a gate, because judges reward length and gating would let a model
win by truncating.
"""

CYRILLIC_FLOOR = 0.70
MIN_BULLETS = 5
BULLET_MARKERS = ("-", "*", "•", "–", "—")

PREAMBLES = (
    "вот ",
    "вот,",
    "конечно",
    "ниже ",
    "ниже,",
    "итак",
    "разумеется",
    "в этой статье",
    "в данной статье",
    "в этом видео",
    "в данном видео",
    "данный текст",
    "этот текст",
    "данная статья",
    "эта статья",
    "краткое содержание",
    "резюме:",
    "суть:",
    "содержание:",
    "here is",
    "here's",
    "sure",
    "certainly",
    "this article",
    "this video",
    "this transcript",
    "in this ",
    "below is",
    "summary:",
)

ARTIFACTS = (
    "[музыка]",
    "[music]",
    "[смех]",
    "[laughter]",
    "[аплодисменты]",
    "[applause]",
    "[музика]",
    "транскрипт",
    "расшифровк",
    "the transcript",
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


def _strip_marker(line):
    for marker in BULLET_MARKERS:
        if line.startswith(marker):
            line = line[len(marker) :]
            break
    return line.strip().lstrip("*_#> ").strip()


def _number(value):
    """Coerce a metadata value to a float.

    The experiment runtime hands item metadata to the evaluator with its values
    stringified, so `char_length` arrives as "19845" even though the dataset
    item stores the JSON number 19845. Dividing by it raises TypeError, which
    discards every score built so far — the failure is silent from outside.
    """
    try:
        return float(value)
    except TypeError, ValueError:
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
            Score(name=name, value=passed, data_type="BOOLEAN", comment=comment),
        )

    ratio = _cyrillic_ratio(output)
    add(
        "t1_language_match",
        ratio >= CYRILLIC_FLOOR,
        f"Cyrillic share of letters: {ratio:.2f} (floor {CYRILLIC_FLOOR}).",
    )

    first = _strip_marker(lines[0]).lower() if lines else ""
    hit = next((p for p in PREAMBLES if first.startswith(p)), None)
    add(
        "t1_no_preamble",
        hit is None,
        "Starts with the summary." if hit is None else f"Opens with preamble {hit!r}.",
    )

    lowered = output.lower()
    found = [a for a in ARTIFACTS if a in lowered]
    add(
        "t1_no_artifacts",
        not found,
        "No transcript artifacts." if not found else f"Leaked: {', '.join(found)}.",
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
        stray = [line for line in lines if not _is_bullet(line)]
        add(
            "t1_bullet_purity",
            not stray,
            "Every line is a bullet."
            if not stray
            else f"{len(stray)} non-bullet line(s), first: {stray[0][:60]!r}.",
        )

    compression = min(len(output) / source_chars, 1.0) if source_chars else 0.0
    scores.append(
        Score(
            name="t1_compression",
            value=compression,
            data_type="NUMERIC",
            comment=f"{len(output)} output chars / {source_chars:.0f} source chars.",
        ),
    )

    failed = [name for name, ok in binary.items() if not ok]
    scores.append(
        Score(
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

    return EvaluationResult(scores=scores)
