"""Price history charts rendered with matplotlib (Agg backend, no display)."""
from __future__ import annotations

import datetime
import tempfile
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

CHART_REFRESH_DAYS = 30
MIN_HISTORY_POINTS = 10

_CURRENCY_SYMBOLS = {"EUR": "€", "GBP": "£", "USD": "$"}


def should_send_auto_chart(item: dict[str, Any]) -> bool:
    if item.get("paused"):
        return False
    if item.get("mode") == "page_diff":
        return False
    target = item.get("target_price")
    last_price = item.get("last_price")
    if target is not None and last_price is not None and last_price <= target:
        return False
    history = item.get("history", [])
    if len(history) < MIN_HISTORY_POINTS:
        return False
    last_sent = item.get("last_chart_sent")
    if last_sent is None:
        return True
    last_sent_date = datetime.datetime.fromisoformat(last_sent).date()
    today = datetime.datetime.now(datetime.timezone.utc).date()
    days_since = (today - last_sent_date).days
    return days_since >= CHART_REFRESH_DAYS


def render_chart(item: dict[str, Any]) -> str:
    history = item.get("history", [])
    dates = [h["d"] for h in history]
    prices = [h["p"] / 100 for h in history]
    currency = item.get("currency", "EUR")
    symbol = _CURRENCY_SYMBOLS.get(currency, currency + " ")

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.step(dates, prices, where="post", label="price")

    target = item.get("target_price")
    if target is not None:
        ax.axhline(target / 100, linestyle="--", color="red", label="target")

    ax.set_title(item["label"])
    ax.set_ylabel(f"Price ({symbol})")
    ax.tick_params(axis="x", rotation=45)
    if len(dates) > 15:
        step = max(1, len(dates) // 15)
        ax.set_xticks(range(0, len(dates), step))
        ax.set_xticklabels([dates[i] for i in range(0, len(dates), step)])
    ax.legend()
    fig.tight_layout()

    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)  # noqa: SIM115 - caller owns the file
    fig.savefig(tmp.name)
    plt.close(fig)
    return tmp.name
