from src.commands import _derive_selector

NESTED_PRICE = """
<html><body>
<span class="woocommerce-Price-amount">
  <bdi>249.00<span class="woocommerce-Price-currencySymbol">&euro;</span></bdi>
</span>
<span class="screen-reader-text">Current price is: &euro;249.00.</span>
</body></html>
"""

SIMPLE_PRICE = """
<html><body><span class="price">19.99</span></body></html>
"""


def test_matches_by_value_not_literal_text():
    # User types the price with a currency symbol; the page node doesn't have one.
    selector = _derive_selector(NESTED_PRICE, "€249.00")
    assert selector == "bdi"


def test_matches_plain_decimal():
    selector = _derive_selector(SIMPLE_PRICE, "19.99")
    assert selector == "span.price"


def test_unparseable_literal_returns_none():
    assert _derive_selector(SIMPLE_PRICE, "not a price") is None


def test_no_matching_value_returns_none():
    assert _derive_selector(SIMPLE_PRICE, "5.00") is None
