"""Tests for the Tier 1 code evaluator that Langfuse runs on every summary.

The module runs on Langfuse's interpreter with `Score` and `EvaluationResult`
injected into its globals, so the tests inject stand-ins the same way.
"""

import ast
from types import SimpleNamespace

import pytest

from helpers import EVAL_DIR, load_eval_script

SOURCE = EVAL_DIR / "tier1_evaluator.py"
# The oldest interpreter the uploaded source must still parse on. Langfuse does
# not publish its runtime's version, so this is a conservative floor.
OLDEST_RUNTIME = (3, 9)

RUSSIAN_BULLETS = "\n".join(
    f"- Пункт {i}: автор объясняет главную мысль источника." for i in range(1, 6)
)


@pytest.fixture
def tier1(monkeypatch):
    """The module, with the names Langfuse injects stubbed in."""
    module = load_eval_script(monkeypatch, "tier1_evaluator")
    module.Score = SimpleNamespace
    module.EvaluationResult = lambda scores: SimpleNamespace(scores=scores)
    return module


def _ctx(output, *, item_meta=None, obs_meta=None, experiment=True):
    return SimpleNamespace(
        observation=SimpleNamespace(output=output, metadata=obs_meta),
        experiment=(SimpleNamespace(item_metadata=item_meta) if experiment else None),
    )


def _scores(result):
    return {s.name: s for s in result.scores}


def _values(result):
    return {s.name: s.value for s in result.scores}


# --- portability -----------------------------------------------------------------


def test_source_parses_on_the_oldest_runtime():
    """Newer syntax is a SyntaxError on Langfuse, which reads as no scores at all."""
    ast.parse(SOURCE.read_text(), feature_version=OLDEST_RUNTIME)


def test_the_parse_check_catches_pep_758():
    """The check above would catch what a py314 formatter writes."""
    with pytest.raises(SyntaxError):
        ast.parse(
            "try:\n    pass\nexcept A, B:\n    pass\n",
            feature_version=OLDEST_RUNTIME,
        )


def test_runtime_injected_names_are_not_shadowed():
    """Defining or importing `Score` would replace the one Langfuse injects."""
    tree = ast.parse(SOURCE.read_text())
    bound = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            bound.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            bound.update((a.asname or a.name).split(".")[0] for a in node.names)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            bound.add(node.id)
    assert not bound & {"Score", "EvaluationResult"}


# --- evaluate --------------------------------------------------------------------


def test_clean_russian_bullets_pass_every_check(tier1):
    """A well-formed summary passes every applicable check."""
    result = tier1.evaluate(
        _ctx(
            RUSSIAN_BULLETS,
            item_meta={"prompt_key": "key_points_for_transcript", "char_length": 1000},
        ),
    )
    values = _values(result)
    assert values == {
        "t1_language_match": True,
        "t1_script_clean": True,
        "t1_compression": pytest.approx(len(RUSSIAN_BULLETS) / 1000),
        "t1_pass": True,
    }
    assert _scores(result)["t1_pass"].comment == "All 2 applicable checks passed."


def test_english_summary_fails_language_and_the_pass(tier1):
    """A summary in the wrong language fails the gate."""
    result = tier1.evaluate(_ctx("- An English summary of the source.\n" * 5))
    values = _values(result)
    assert values["t1_language_match"] is False
    assert values["t1_pass"] is False
    assert _scores(result)["t1_pass"].comment == "Failed: t1_language_match."


def test_a_single_cjk_leak_fails_the_script_check(tier1):
    """Two CJK characters barely move the Cyrillic share; this check sees them."""
    result = tier1.evaluate(_ctx(RUSSIAN_BULLETS + " 复杂"))
    values = _values(result)
    assert values["t1_language_match"] is True
    assert values["t1_script_clean"] is False
    assert values["t1_pass"] is False
    assert "复杂" in _scores(result)["t1_script_clean"].comment


def test_latin_greek_and_diacritics_are_allowed(tier1):
    """Names, symbols and diacritics are not a script leak."""
    result = tier1.evaluate(_ctx(RUSSIAN_BULLETS + " OpenAI, Δ, μ, café, Łódź"))
    assert _values(result)["t1_script_clean"] is True


@pytest.mark.parametrize(
    ("char_length", "compression"),
    [
        ("200", 0.5),  # the runtime stringifies metadata values
        (200, 0.5),
        (50, 1.0),  # capped: a summary longer than its source is not "more"
        (None, 0.0),
        ("not a number", 0.0),
    ],
)
def test_compression_reads_stringified_metadata(tier1, char_length, compression):
    """`char_length` may arrive as a string, or not at all."""
    output = "ж" * 100
    result = tier1.evaluate(_ctx(output, item_meta={"char_length": char_length}))
    assert _values(result)["t1_compression"] == pytest.approx(compression)


def test_scores_a_trace_outside_an_experiment(tier1):
    """A live trace, with no experiment metadata, still scores."""
    result = tier1.evaluate(_ctx(RUSSIAN_BULLETS, experiment=False))
    assert _values(result)["t1_pass"] is True
    assert _values(result)["t1_compression"] == 0.0


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (None, ""),
        ("plain", "plain"),
        ({"content": "a"}, "a"),
        ({"output": {"text": "nested"}}, "nested"),
        (["a", {"value": "b"}], "a\nb"),
        (42, "42"),
    ],
)
def test_text_flattens_recorded_output(tier1, value, text):
    """Any recorded output shape becomes plain text."""
    assert tier1._text(value) == text


def test_empty_output_fails_language(tier1):
    """No output has no Cyrillic share to pass on."""
    assert _values(tier1.evaluate(_ctx(None)))["t1_language_match"] is False
