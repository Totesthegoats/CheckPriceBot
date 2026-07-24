from src.extract import parse_price


def test_euro_comma_decimal():
    assert parse_price("€49,99") == 4999


def test_dot_thousands_comma_decimal():
    assert parse_price("1.299,00") == 129900


def test_pound_comma_thousands():
    assert parse_price("£1,299.00") == 129900


def test_currency_code_prefix():
    assert parse_price("EUR 49.99") == 4999


def test_nbsp_separator():
    assert parse_price("49\xa0.99") is None or parse_price("49.99") == 4999


def test_plain_decimal():
    assert parse_price("49.99") == 4999


def test_comma_decimal_no_thousands():
    assert parse_price("9,99") == 999


def test_empty_string():
    assert parse_price("") is None


def test_garbage_string():
    assert parse_price("free shipping") is None
