from src.extract import extract_json_ld

SIMPLE = """
<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Product","name":"Widget",
 "offers":{"@type":"Offer","price":"49.99","priceCurrency":"EUR"}}
</script>
</head><body></body></html>
"""

ARRAY = """
<html><head>
<script type="application/ld+json">
[{"@type":"Product","offers":{"price":"19.99","priceCurrency":"GBP"}}]
</script>
</head></html>
"""

GRAPH = """
<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@graph":[
  {"@type":"WebPage"},
  {"@type":"Product","offers":{"price":"9.50","priceCurrency":"USD"}}
]}
</script>
</head></html>
"""

MULTI_OFFER = """
<html><head>
<script type="application/ld+json">
{"@type":"Product","offers":[{"price":"5.00","priceCurrency":"EUR"},{"price":"6.00"}]}
</script>
</head></html>
"""

NO_PRODUCT = """
<html><head>
<script type="application/ld+json">
{"@type":"BreadcrumbList"}
</script>
</head></html>
"""

PRICE_SPECIFICATION = """
<html><head>
<script type="application/ld+json">
{"@type":"Product","offers":[{"@type":"Offer","priceSpecification":[
  {"@type":"UnitPriceSpecification","price":"249.00","priceCurrency":"EUR"},
  {"@type":"UnitPriceSpecification","price":"307.00","priceCurrency":"EUR","priceType":"https://schema.org/ListPrice"}
]}]}
</script>
</head></html>
"""


def test_simple_object():
    result = extract_json_ld(SIMPLE)
    assert result is not None
    assert result.price_cents == 4999
    assert result.currency == "EUR"


def test_top_level_array():
    result = extract_json_ld(ARRAY)
    assert result is not None
    assert result.price_cents == 1999
    assert result.currency == "GBP"


def test_at_graph_wrapper():
    result = extract_json_ld(GRAPH)
    assert result is not None
    assert result.price_cents == 950
    assert result.currency == "USD"


def test_multiple_offers_takes_first():
    result = extract_json_ld(MULTI_OFFER)
    assert result is not None
    assert result.price_cents == 500


def test_no_product_returns_none():
    assert extract_json_ld(NO_PRODUCT) is None


def test_no_script_returns_none():
    assert extract_json_ld("<html><body>no scripts here</body></html>") is None


def test_price_nested_under_price_specification():
    """WooCommerce's schema plugin nests price under offers[].priceSpecification[]
    instead of directly on the offer, using priceType to mark a strikethrough list price."""
    result = extract_json_ld(PRICE_SPECIFICATION)
    assert result is not None
    assert result.price_cents == 24900
    assert result.currency == "EUR"
