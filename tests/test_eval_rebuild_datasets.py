"""Regression tests for the destructive dataset wipe."""

import hashlib
import importlib.util
import json
import random
import string
from pathlib import Path

import pytest


@pytest.fixture
def rebuild(monkeypatch):
    """Load the script as a module without running its CLI."""
    directory = Path(__file__).resolve().parents[1] / "scripts" / "eval"
    monkeypatch.syspath_prepend(str(directory))
    spec = importlib.util.spec_from_file_location(
        "eval_rebuild_datasets_test",
        directory / "rebuild_datasets.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pages(mocker, *pages):
    responses = []
    for page in pages:
        response = mocker.Mock()
        response.json.return_value = {"data": [{"id": i} for i in page]}
        responses.append(response)
    return responses


def test_wipe_deletes_every_page_until_empty(rebuild, mocker):
    """Pages are deleted until the listing comes back empty."""
    get = mocker.patch.object(
        rebuild.requests,
        "get",
        side_effect=_pages(mocker, ["a", "b"], ["c"], []),
    )
    delete = mocker.patch.object(rebuild.requests, "delete")
    assert rebuild.wipe("dataset") == 3
    assert get.call_count == 3
    assert delete.call_count == 3


def test_wipe_exits_when_deleted_items_are_listed_again(rebuild, mocker):
    """A deleted item listed again stops the wipe instead of looping forever."""
    mocker.patch.object(
        rebuild.requests,
        "get",
        side_effect=_pages(mocker, ["a", "b"], ["b", "c"]),
    )
    delete = mocker.patch.object(rebuild.requests, "delete")
    with pytest.raises(SystemExit, match="still listed"):
        rebuild.wipe("dataset")
    assert delete.call_count == 2


# --- selecting the pool ---------------------------------------------------------


def _blob(seed, chars=2000):
    """Prose-like text that is neither degenerate nor shaped like subtitles."""
    rng = random.Random(seed)  # noqa: S311 - fixture text, not a secret
    words = []
    while sum(len(w) + 1 for w in words) < chars:
        words.append("".join(rng.choice(string.ascii_lowercase) for _ in range(6)))
    return f"{seed} " + " ".join(words)


def _row(text, summary="Краткое изложение источника на русском.", language="Russian"):
    """A traced generation as the `openai` SDK's Langfuse drop-in records it."""
    return {
        "input": json.dumps(
            [
                {"role": "system", "content": "INSTRUCTIONS"},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "PROMPT"},
                        {"type": "text", "text": text},
                    ],
                },
            ],
        ),
        "output": json.dumps({"role": "assistant", "content": summary}),
        "metadata": {"target_language": language},
    }


def _legacy_row(text, summary):
    """The same generation in the shape pydantic-ai traced."""
    return {
        "input": json.dumps(
            [{"role": "system"}, {"parts": [{"content": "PROMPT"}, {"content": text}]}],
        ),
        "output": json.dumps(
            [
                {
                    "parts": [
                        {"type": "thinking", "content": "reasoning in English"},
                        {"type": "text", "content": summary},
                    ],
                },
            ],
        ),
    }


def test_content_of_reads_the_second_part(rebuild):
    """The source is the second part of the user message."""
    assert rebuild.content_of(_row("the source")) == "the source"
    only_prompt = {
        "input": json.dumps(
            [{}, {"role": "user", "content": [{"type": "text", "text": "PROMPT"}]}],
        ),
    }
    assert rebuild.content_of(only_prompt) == ""
    assert rebuild.content_of({"input": "not json"}) is None


def test_summary_of_reads_the_assistant_message(rebuild):
    """The summary is the reply's content; a reply without one counts as empty."""
    assert rebuild.summary_of(_row("x")) == "Краткое изложение источника на русском."
    assert rebuild.summary_of(_row("x", summary=None)) == ""
    assert rebuild.summary_of({"output": "not json"}) == ""


def test_legacy_traces_are_still_read(rebuild):
    """A harvest reaching back before the SDK switch holds pydantic-ai's shape too."""
    row = _legacy_row("the source", "the summary")
    assert rebuild.content_of(row) == "the source"
    assert rebuild.summary_of(row) == "the summary"
    only_prompt = {"input": json.dumps([{}, {"parts": [{"content": "PROMPT"}]}])}
    assert rebuild.content_of(only_prompt) == ""


@pytest.mark.parametrize(
    ("text", "stratum"),
    [
        ("\n".join(["a short subtitle line"] * 30), "yt_transcript"),
        ("<html><body>article</body></html>", "web_article"),
        ("See [the docs](https://example.test) for more.", "web_article"),
        (_blob(1), "audio_transcript"),
    ],
)
def test_stratum_of(rebuild, text, stratum):
    """Each source kind is recognised by its shape."""
    assert rebuild.stratum_of(text) == stratum


def test_is_degenerate_catches_repetition(rebuild):
    """Text that compresses to almost nothing is rejected."""
    assert rebuild.is_degenerate("the same phrase again " * 200)
    assert not rebuild.is_degenerate(_blob(1))


def test_pool_keeps_only_usable_distinct_sources(rebuild):
    """Duplicates, short, degenerate and failed-language rows are dropped."""
    good, other = _blob(1), _blob(2)
    rows = [
        _row(good),
        _row(good),  # exact duplicate
        _row(good.upper()),  # same opening, differently cased
        _row(other, summary="An English summary failed Tier 1 language."),
        _row(_blob(3), language=None),
        _row(_blob(4, chars=500)),  # too short
        _row("the same phrase again " * 200),  # degenerate
        {"input": "not json", "output": "", "metadata": {}},
    ]
    picked = rebuild.pool(rows)
    assert [text for _, text, _ in picked] == [good]
    assert picked[0][0] == hashlib.sha256(good.encode()).hexdigest()[:12]


def test_select_fills_each_quota_mixing_long_and_short(rebuild):
    """Two long then one short, so no stratum's quota is all one length."""
    long_ = [(f"l{i}", _blob(i, chars=rebuild.LONG_CHARS), None) for i in range(3)]
    short = [(f"s{i}", _blob(10 + i), None) for i in range(2)]
    web = [("w0", "<html>page</html>", None)]

    picked = rebuild.select(
        short + long_ + web,
        {"audio_transcript": 4, "web_article": 3, "yt_transcript": 1},
    )

    assert [digest for digest, _, _ in picked] == ["l0", "l1", "s0", "l2", "w0"]
