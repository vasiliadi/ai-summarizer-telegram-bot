from prompts import PROMPTS, prompt_version


def test_prompt_version_is_a_stable_short_hex_digest():
    """prompt_version returns the same short hex digest for repeated calls."""
    version = prompt_version("basic_prompt_for_transcript")

    assert version == prompt_version("basic_prompt_for_transcript")
    assert len(version) == 12
    assert int(version, 16) >= 0


def test_prompt_version_differs_between_strategies():
    """Each prompt strategy gets its own version."""
    versions = {prompt_version(key) for key in PROMPTS}

    assert len(versions) == len(PROMPTS)


def test_prompt_version_moves_when_the_prompt_is_reworded(mocker):
    """Editing a prompt template changes that key's version."""
    before = prompt_version("basic_prompt_for_transcript")
    mocker.patch.dict(
        "prompts.PROMPTS",
        {"basic_prompt_for_transcript": "Reworded."},
    )

    assert prompt_version("basic_prompt_for_transcript") != before


def test_prompt_version_moves_when_the_system_instruction_is_reworded(mocker):
    """Editing the shared system instruction changes every key's version.

    The prompt key alone cannot express this, which is the reason the version
    hashes both templates rather than the strategy's own text.
    """
    before = prompt_version("basic_prompt_for_transcript")
    mocker.patch("prompts.SYSTEM_INSTRUCTION", "Reworded system instruction.")

    assert prompt_version("basic_prompt_for_transcript") != before
