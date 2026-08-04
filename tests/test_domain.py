from domain import PrefixedText, format_prefixed_summary


def test_format_prefixed_summary_preserves_blank_line():
    """Test prefixed summaries always include exactly one blank line."""
    assert format_prefixed_summary("📹", "\n- one\n- two\n") == "📹\n\n- one\n- two"


def test_prefixed_text_pairs_content_with_its_source_prefix():
    """Test PrefixedText carries the extracted text and its display prefix."""
    result = PrefixedText(text="content", prefix="🌐")

    assert result.text == "content"
    assert result.prefix == "🌐"
