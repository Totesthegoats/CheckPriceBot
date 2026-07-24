from src.telegram import parse_chat_ids


def test_single_chat_id():
    assert parse_chat_ids("123456789") == ["123456789"]


def test_comma_separated_chat_ids():
    assert parse_chat_ids("123,456, 789") == ["123", "456", "789"]


def test_strips_whitespace():
    assert parse_chat_ids(" 111 , 222 ") == ["111", "222"]


def test_ignores_empty_segments():
    assert parse_chat_ids("111,,222,") == ["111", "222"]
