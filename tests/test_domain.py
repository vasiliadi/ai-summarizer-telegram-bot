from domain import format_prefixed_summary


def test_format_prefixed_summary_preserves_blank_line():
    """Test prefixed summaries always include exactly one blank line."""
    assert format_prefixed_summary("📹", "\n- one\n- two\n") == "📹\n\n- one\n- two"
