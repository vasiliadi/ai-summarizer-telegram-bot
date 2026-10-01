"""Tests for the Tier 2 judges and the compare-run task.

No judge is called: `_post` is patched, so these pin what goes out, how each
answer is reduced to a score, and what the task hands the bot's client.
"""

import asyncio
import io
import json
from textwrap import dedent
from types import SimpleNamespace

import pytest

from helpers import load_eval_script
from prompts import PROMPTS, prompt_version

SOURCE = "The source says the launch happened in March."
SUMMARY = "- Запуск прошёл в марте.\n\n* Компания выросла.\n• Итог."


@pytest.fixture
def judge(monkeypatch):
    """The module, loaded fresh with the real `eval_client` and `src` imports."""
    return load_eval_script(monkeypatch, "judge")


# --- reading items -----------------------------------------------------------


@pytest.mark.parametrize(
    ("output", "failed"),
    [
        ("", True),
        ("  \n", True),
        ("Error: RuntimeError('boom')", True),
        ("- a summary", False),
        ("- a summary that mentions Error: in passing", False),
    ],
)
def test_generation_failed(judge, output, failed):
    """An empty or `Error:` output is a failed generation, nothing else."""
    assert judge.generation_failed(output) is failed


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (None, ""),
        ("plain", "plain"),
        ({"text": "a"}, "a"),
        (["a", {"content": "b"}], "a\nb"),
        ({"unknown": "ж"}, '{"unknown": "ж"}'),
        (3, "3"),
    ],
)
def test_text_flattens_recorded_output(judge, value, text):
    """Any recorded output shape becomes plain text."""
    assert judge._text(value) == text


def test_source_of_reads_item_content(judge):
    """The source is the item's `content`, or the input itself when text."""
    assert judge._source_of({"content": "src", "target_language": "Russian"}) == "src"
    assert judge._source_of({"target_language": "Russian"}) == ""
    assert judge._source_of("already text") == "already text"


def test_bullets_of_strips_markers_and_blank_lines(judge):
    """Every non-empty line is one bullet, marker stripped."""
    assert judge.bullets_of(SUMMARY) == [
        "Запуск прошёл в марте.",
        "Компания выросла.",
        "Итог.",
    ]


# --- pins --------------------------------------------------------------------


def test_pins_have_a_stable_shape(judge):
    """Each pin names its model and a 12-hex prompt digest."""
    assert judge.jev_meta()["judge_model"] == judge.JEV_MODEL
    assert judge.jev_meta()["judge_prompt"].startswith("jev-supported@")
    assert len(judge.jev_meta()["judge_prompt"].split("@")[1]) == 12
    meta = judge.fabricated_meta()
    assert meta["judge_model"] == judge.FABRICATED_MODEL
    assert meta["judge_effort"] == judge.FABRICATED_EFFORT
    assert meta["judge_prompt"].startswith("fabricated@")


def test_editing_a_judge_prompt_moves_its_pin(judge, monkeypatch):
    """A changed prompt must not bank scores under the old prompt's pin."""
    jev, opus = (
        judge.jev_meta()["judge_prompt"],
        judge.fabricated_meta()["judge_prompt"],
    )
    monkeypatch.setattr(judge, "JEV_SUPPORTED", judge.JEV_SUPPORTED + " ")
    monkeypatch.setattr(judge, "FABRICATED_SCHEMA", {**judge.FABRICATED_SCHEMA, "x": 1})
    assert judge.jev_meta()["judge_prompt"] != jev
    assert judge.fabricated_meta()["judge_prompt"] != opus


# --- HTTP --------------------------------------------------------------------


def test_post_sends_the_key_and_the_apps_attribution(judge, mocker, monkeypatch):
    """Judge spend is this repo's spend, attributed like the bot's own calls."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    response = mocker.MagicMock()
    response.__enter__.return_value = io.BytesIO(b'{"ok": 1}')
    urlopen = mocker.patch.object(
        judge.urllib.request,
        "urlopen",
        return_value=response,
    )

    assert judge._post("https://example.test/x", {"a": 1}, timeout=7) == {"ok": 1}

    request = urlopen.call_args.args[0]
    headers = {k.lower(): v for k, v in request.header_items()}
    assert headers["authorization"] == "Bearer sk-test"
    assert headers["http-referer"] == judge.config.OPENROUTER_APP_URL
    assert headers["x-title"] == judge.config.OPENROUTER_APP_TITLE
    assert json.loads(request.data) == {"a": 1}
    assert urlopen.call_args.kwargs["timeout"] == 7


def test_jev_asks_one_question_per_bullet_in_one_call(judge, mocker):
    """Bullets go out as keyed questions and come back in bullet order."""
    post = mocker.patch.object(
        judge,
        "_post",
        return_value={
            # The reply's shape as observed on 2026-09-30.
            "model": "typesafe/jev-1.13-20260917",
            # Answers out of order: they are matched by key, not position.
            "answers": {"b01": {"noul": 0.2}, "b00": {"noul": 0.9}},
            "usage": {"cost": 0.02},
        },
    )

    probabilities, cost, version = judge.jev_probabilities(
        SOURCE,
        ["first", "second"],
    )

    assert probabilities == [0.9, 0.2]
    assert cost == 0.02
    assert version == "typesafe/jev-1.13-20260917"
    url, body = post.call_args.args
    assert url == judge.DECISIONS_URL
    assert body["model"] == judge.JEV_MODEL
    assert body["state"] == {"source": SOURCE}  # the whole source, never cut
    assert list(body["questions"]) == ["b00", "b01"]
    assert "«first»" in body["questions"]["b00"]["instructions"]
    assert body["questions"]["b00"]["criteria"] == judge.JEV_SUPPORTED_CRITERIA


def test_jev_reply_without_usage_or_model_still_scores(judge, mocker):
    """A missing cost is zero and a missing snapshot is unknown, not a failure."""
    mocker.patch.object(judge, "_post", return_value={"answers": {"b00": {"noul": 1}}})
    assert judge.jev_probabilities(SOURCE, ["one"]) == ([1], 0, None)


def _opus_reply(content, finish_reason="stop", usage=None):
    return {
        "choices": [
            {"message": {"content": content}, "finish_reason": finish_reason},
        ],
        "usage": usage or {"cost": 0.06},
    }


def test_opus_asks_for_the_schema_and_returns_usage(judge, mocker):
    """The call pins model, effort, pricing and the verdict schema."""
    post = mocker.patch.object(
        judge,
        "_post",
        return_value=_opus_reply('{"findings": []}'),
    )

    verdict, usage = judge.ask_fabricated(SOURCE, SUMMARY)

    assert verdict == {"findings": []}
    assert usage == {"cost": 0.06}
    body = post.call_args.args[1]
    assert body["model"] == judge.FABRICATED_MODEL
    assert body["reasoning"] == {"effort": judge.FABRICATED_EFFORT}
    assert body["usage"] == {"include": True}
    assert body["response_format"]["json_schema"]["schema"] == judge.FABRICATED_SCHEMA
    assert SOURCE in body["messages"][0]["content"]
    assert SUMMARY in body["messages"][0]["content"]


@pytest.mark.parametrize("content", [None, "{}", '{"verdict": "fine"}'])
def test_opus_verdict_without_findings_fails_loudly(judge, mocker, content):
    """A truncated verdict must not score as a clean summary."""
    mocker.patch.object(judge, "_post", return_value=_opus_reply(content, "length"))
    with pytest.raises(RuntimeError, match=r"missing findings \(length\)"):
        judge.ask_fabricated(SOURCE, SUMMARY)


# --- evaluators --------------------------------------------------------------


def test_eval_jev_scores_the_weakest_bullet(judge, mocker):
    """One invented bullet among sound ones is what the score must show."""
    mocker.patch.object(
        judge,
        "jev_probabilities",
        return_value=([0.9, 0.1, 0.8], 0.02, "typesafe/jev-1.13-20260917"),
    )

    evaluation = judge.eval_jev(input={"content": SOURCE}, output=SUMMARY)

    assert evaluation.name == "t2_jev_weakest"
    assert evaluation.value == 0.1
    assert evaluation.comment == "bullet 2: Компания выросла."
    assert evaluation.metadata == {
        **judge.jev_meta(),
        "judge_model_version": "typesafe/jev-1.13-20260917",
        "cost": 0.02,
    }


@pytest.mark.parametrize(
    ("item_input", "output"),
    [
        ({"content": ""}, SUMMARY),
        ({"content": SOURCE}, ""),
        ({"content": SOURCE}, "\n"),
    ],
)
def test_eval_jev_skips_items_with_nothing_to_judge(judge, mocker, item_input, output):
    """No source or no bullets means no paid call and no score."""
    ask = mocker.patch.object(judge, "jev_probabilities")
    assert judge.eval_jev(input=item_input, output=output) is None
    ask.assert_not_called()


@pytest.mark.parametrize(
    ("kinds", "value", "counts"),
    [
        ([], 1.0, "0 invented/0 compression. none"),
        (["compression", "compression"], 1.0, "0 invented/2 compression. none"),
        (["compression", "invented"], 0.0, "1 invented/1 compression. claim 1"),
    ],
)
def test_eval_fabricated_fails_only_on_invented(judge, mocker, kinds, value, counts):
    """Compression is what summarising does; only an invented claim fails."""
    findings = [
        {"claim": f"claim {i}", "source_says": "", "kind": kind}
        for i, kind in enumerate(kinds)
    ]
    mocker.patch.object(
        judge,
        "ask_fabricated",
        return_value=({"findings": findings}, {"cost": 0.06}),
    )

    evaluation = judge.eval_fabricated(input={"content": SOURCE}, output=SUMMARY)

    assert evaluation.name == "t2_fabricated"
    assert evaluation.value == value
    assert evaluation.comment == counts
    assert evaluation.metadata["invented"] == kinds.count("invented")
    assert evaluation.metadata["compression"] == kinds.count("compression")
    assert evaluation.metadata["cost"] == 0.06
    assert (
        evaluation.metadata["judge_prompt"] == judge.fabricated_meta()["judge_prompt"]
    )


def test_eval_fabricated_skips_items_with_nothing_to_judge(judge, mocker):
    """An empty summary means no paid call and no score."""
    ask = mocker.patch.object(judge, "ask_fabricated")
    assert judge.eval_fabricated(input={"content": SOURCE}, output="") is None
    ask.assert_not_called()


def test_judges_by_name(judge):
    """Each `--tier2` name selects its evaluators."""
    assert {
        "jev": [judge.eval_jev],
        "opus": [judge.eval_fabricated],
        "none": [],
    } == judge.JUDGES


# --- the task ----------------------------------------------------------------


def test_compare_strategy_is_a_real_prompt(judge):
    """The default strategy has to exist in the bot's prompt table."""
    assert judge.PROMPT_KEY in PROMPTS


@pytest.mark.parametrize(
    ("item_input", "language"),
    [
        ({"content": SOURCE}, "Russian"),
        ({"content": SOURCE, "target_language": "English"}, "English"),
    ],
)
def test_task_summarises_with_the_bots_prompt(judge, mocker, item_input, language):
    """The candidate gets the bot's own prompt, dedented as `summarize_text` does."""
    summarize = mocker.patch.object(
        judge,
        "summarize",
        mocker.AsyncMock(return_value="s"),
    )
    task = judge.make_task("vendor/m", judge.PROMPT_KEY)

    result = asyncio.run(task(item=SimpleNamespace(input=item_input)))

    assert result == "s"
    summarize.assert_awaited_once_with(
        "vendor/m",
        dedent(PROMPTS[judge.PROMPT_KEY]).strip(),
        SOURCE,
        language,
    )


def test_run_names_the_candidate_and_warns_about_failed_items(judge, mocker, capsys):
    """The run carries its strategy as `run_prompt_key`, and failures are reported.

    A raised task is absent from `item_results` (the SDK drops it); an empty one is not.
    """
    client = mocker.Mock()
    client.get_dataset.return_value.items = ["raised", "empty", "fine"]
    client.run_experiment.return_value = SimpleNamespace(
        run_name="stage2 / vendor/m / key - now",
        item_results=[
            SimpleNamespace(
                item=SimpleNamespace(id="item-2"),
                output="",
                evaluations=[],
            ),
            SimpleNamespace(
                item=SimpleNamespace(id="item-3"),
                output="- summary",
                evaluations=[SimpleNamespace(name="t2_jev_weakest", value=0.9)],
            ),
        ],
    )
    mocker.patch.object(judge, "Langfuse", return_value=client)
    mocker.patch.object(judge.config, "langfuse_client", None)

    judge.run("vendor/m", "dataset", judge.PROMPT_KEY, tier2="opus")

    kwargs = client.run_experiment.call_args.kwargs
    assert kwargs["name"] == f"{judge.RUN_PREFIX}vendor/m / {judge.PROMPT_KEY}"
    assert kwargs["data"] == ["raised", "empty", "fine"]
    assert kwargs["evaluators"] == [judge.eval_fabricated]
    assert kwargs["metadata"]["run_prompt_key"] == judge.PROMPT_KEY
    assert "prompt_key" not in kwargs["metadata"]
    assert kwargs["metadata"]["prompt_version"] == prompt_version(judge.PROMPT_KEY)
    assert kwargs["metadata"]["candidate_model"] == "vendor/m"
    assert kwargs["metadata"]["tier2_judge"] == "opus"
    client.flush.assert_called_once()
    output = capsys.readouterr().out
    assert "WARNING: 2/3 items failed to generate" in output


def test_run_is_quiet_when_every_item_generates(judge, mocker, capsys):
    """No warning when every dataset item comes back with a summary."""
    client = mocker.Mock()
    client.get_dataset.return_value.items = ["fine"]
    client.run_experiment.return_value = SimpleNamespace(
        run_name="stage2 / vendor/m / key - now",
        item_results=[
            SimpleNamespace(
                item=SimpleNamespace(id="item-1"),
                output="- summary",
                evaluations=[],
            ),
        ],
    )
    mocker.patch.object(judge, "Langfuse", return_value=client)
    mocker.patch.object(judge.config, "langfuse_client", None)

    judge.run("vendor/m", "dataset", judge.PROMPT_KEY)

    assert "WARNING" not in capsys.readouterr().out
