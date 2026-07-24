"""Shared helpers for building/formatting watchlist item dicts."""
from __future__ import annotations

import datetime
from typing import Any


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def today() -> str:
    return datetime.datetime.now(datetime.timezone.utc).date().isoformat()


def format_price(cents: int, currency: str) -> str:
    symbol = {"EUR": "€", "GBP": "£", "USD": "$"}.get(currency, currency + " ")
    return f"{symbol}{cents / 100:.2f}"


def new_item(item_id: int, mode: str, url: str, label: str) -> dict[str, Any]:
    return {
        "id": item_id,
        "mode": mode,
        "url": url,
        "label": label,
        "selector": None,
        "currency": "EUR",
        "last_price": None,
        "target_price": None,
        "last_hash": None,
        "paused": False,
        "status": "ok",
        "fail_count": 0,
        "use_proxy": False,
        "history": [],
        "last_chart_sent": None,
        "added": now_iso(),
        "last_checked": None,
    }
