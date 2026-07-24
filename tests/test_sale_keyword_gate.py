from src.snapshots import clean_page_text as _clean_page_text
from src.snapshots import found_sale_keywords as _found_sale_keywords


def test_finds_known_keyword():
    text = _clean_page_text("<html><body>Big Sale this week!</body></html>")
    assert "sale" in _found_sale_keywords(text)


def test_percent_off_keyword():
    text = _clean_page_text("<html><body>Everything 20% off today</body></html>")
    assert "% off" in _found_sale_keywords(text)


def test_no_keywords_present():
    text = _clean_page_text("<html><body>Welcome to our store</body></html>")
    assert _found_sale_keywords(text) == set()


def test_strips_scripts_and_styles():
    html = "<html><body><script>var sale='fake';</script><style>.sale{}</style>Regular price only</body></html>"
    text = _clean_page_text(html)
    assert "sale" not in text.lower()


def test_gate_only_fires_on_new_keywords():
    old_text = _clean_page_text("<html><body>Regular price</body></html>")
    new_text = _clean_page_text("<html><body>Clearance sale now on</body></html>")
    old_keywords = _found_sale_keywords(old_text)
    new_keywords = _found_sale_keywords(new_text)
    newly_appeared = new_keywords - old_keywords
    assert newly_appeared == {"sale", "clearance"}


def test_gate_silent_if_keyword_already_present():
    old_text = _clean_page_text("<html><body>Sale price now</body></html>")
    new_text = _clean_page_text("<html><body>Sale price still now</body></html>")
    old_keywords = _found_sale_keywords(old_text)
    new_keywords = _found_sale_keywords(new_text)
    assert new_keywords - old_keywords == set()
