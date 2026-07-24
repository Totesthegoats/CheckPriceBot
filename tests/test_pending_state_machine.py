import datetime

from src.commands import _resolve_pending
from src.fetch import FetchResult


class FakeTelegram:
    def __init__(self):
        self.messages = []

    def send_message(self, text, chat_id=None):
        self.messages.append(text)

    def send_photo(self, photo_path, caption="", chat_id=None):
        pass


class FakeFetcher:
    def __init__(self, result=None):
        self.result = result or FetchResult(status="ok", text="<html><body>Price: 19.99</body></html>")

    def fetch(self, url):
        return self.result


def _iso(hours_ago: float = 0) -> str:
    dt = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours_ago)
    return dt.isoformat()


def make_item(item_id=1):
    return {
        "id": item_id,
        "mode": "price",
        "url": "https://example.com/p",
        "label": "Widget",
        "selector": None,
        "currency": "EUR",
        "last_price": 2500,
        "target_price": None,
        "last_hash": None,
        "paused": False,
        "status": "ok",
        "fail_count": 0,
        "use_proxy": False,
        "history": [],
        "last_chart_sent": None,
        "added": _iso(),
        "last_checked": None,
    }


def test_target_numeric_resolves_pending():
    watchlist = {"items": [make_item()], "next_id": 2}
    state = {"pending": {"item_id": 1, "awaiting": "target", "created": _iso()}}
    tg = FakeTelegram()
    handled = _resolve_pending("20", watchlist, state, FakeFetcher(), tg)
    assert handled is True
    assert watchlist["items"][0]["target_price"] == 2000
    assert state["pending"] is None


def test_target_none_clears_target():
    watchlist = {"items": [make_item()], "next_id": 2}
    watchlist["items"][0]["target_price"] = 1000
    state = {"pending": {"item_id": 1, "awaiting": "target", "created": _iso()}}
    tg = FakeTelegram()
    handled = _resolve_pending("none", watchlist, state, FakeFetcher(), tg)
    assert handled is True
    assert watchlist["items"][0]["target_price"] is None


def test_non_numeric_does_not_resolve_target_pending():
    watchlist = {"items": [make_item()], "next_id": 2}
    state = {"pending": {"item_id": 1, "awaiting": "target", "created": _iso()}}
    tg = FakeTelegram()
    handled = _resolve_pending("what's the weather", watchlist, state, FakeFetcher(), tg)
    assert handled is False
    assert state["pending"] is not None


def test_expired_pending_is_cleared_and_not_resolved():
    watchlist = {"items": [make_item()], "next_id": 2}
    state = {"pending": {"item_id": 1, "awaiting": "target", "created": _iso(hours_ago=49)}}
    tg = FakeTelegram()
    handled = _resolve_pending("20", watchlist, state, FakeFetcher(), tg)
    assert handled is False
    assert state["pending"] is None


def test_pending_just_under_expiry_still_resolves():
    watchlist = {"items": [make_item()], "next_id": 2}
    state = {"pending": {"item_id": 1, "awaiting": "target", "created": _iso(hours_ago=47)}}
    tg = FakeTelegram()
    handled = _resolve_pending("20", watchlist, state, FakeFetcher(), tg)
    assert handled is True


def test_price_awaiting_derives_selector_and_chains_to_target():
    watchlist = {"items": [make_item()], "next_id": 2}
    watchlist["items"][0]["last_price"] = None
    state = {"pending": {"item_id": 1, "awaiting": "price", "created": _iso()}}
    tg = FakeTelegram()
    fetcher = FakeFetcher(FetchResult(status="ok", text="<html><body><span class='p'>19.99</span></body></html>"))
    handled = _resolve_pending("19.99", watchlist, state, fetcher, tg)
    assert handled is True
    assert watchlist["items"][0]["last_price"] == 1999
    assert state["pending"]["awaiting"] == "target"


def test_no_pending_returns_false():
    watchlist = {"items": [make_item()], "next_id": 2}
    state = {"pending": None}
    tg = FakeTelegram()
    assert _resolve_pending("20", watchlist, state, FakeFetcher(), tg) is False
