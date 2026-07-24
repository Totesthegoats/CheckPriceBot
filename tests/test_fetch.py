from src.fetch import _looks_garbled


def test_normal_html_is_not_garbled():
    assert _looks_garbled("<!doctype html><html><body>Price: 19.99</body></html>") is False


def test_xml_style_page_is_not_garbled():
    assert _looks_garbled("<?xml version='1.0'?><rss><channel></channel></rss>") is False


def test_binary_bytes_decoded_as_text_are_garbled():
    # Simulates Brotli/gzip bytes httpx couldn't decompress, decoded as text.
    garbage = bytes(range(256)).decode("latin-1") * 10
    assert _looks_garbled(garbage) is True


def test_empty_string_is_not_flagged_as_garbled():
    # Empty-body handling belongs to the needs_js check upstream, not this one.
    assert _looks_garbled("") is False


def test_plain_text_with_few_control_chars_is_not_garbled():
    # No html marker, but no binary noise either — shouldn't false-positive.
    text = "Just a moment...\nplease wait while we verify your browser."
    assert _looks_garbled(text) is False
