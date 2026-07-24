"""Per-item check logic for price and page_diff modes."""
from __future__ import annotations

import datetime
import hashlib
from dataclasses import dataclass, field
from typing import Any

from src.extract import extract_price
from src.fetch import Fetcher, FetchResult
from src.snapshots import clean_page_text, found_sale_keywords, load_snapshot, save_snapshot

MAX_HISTORY = 400
FAIL_WARN_THRESHOLD = 3
FAIL_AUTOPAUSE_THRESHOLD = 7


@dataclass
class CheckEvent:
    item: dict[str, Any]
    kind: str  # "price_drop", "target_hit", "sale_detected", "warning", "autopaused"
    message: str


@dataclass
class CheckOutcome:
    events: list[CheckEvent] = field(default_factory=list)
    ask_proxy: list[dict[str, Any]] = field(default_factory=list)
    ask_price: list[dict[str, Any]] = field(default_factory=list)


def _today() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


def _format_price(cents: int, currency: str) -> str:
    symbol = {"EUR": "€", "GBP": "£", "USD": "$"}.get(currency, currency + " ")
    return f"{symbol}{cents / 100:.2f}"


def _record_failure(item: dict[str, Any], reason: str, outcome: CheckOutcome) -> None:
    item["fail_count"] = item.get("fail_count", 0) + 1
    item["status"] = "failing"
    if item["fail_count"] == FAIL_WARN_THRESHOLD:
        outcome.events.append(
            CheckEvent(item, "warning", f"⚠️ {item['label']} has failed {item['fail_count']} checks in a row: {reason}")
        )
    if item["fail_count"] >= FAIL_AUTOPAUSE_THRESHOLD:
        item["paused"] = True
        outcome.events.append(
            CheckEvent(item, "autopaused", f"⏸️ {item['label']} auto-paused after {item['fail_count']} consecutive failures")
        )


def _handle_blocked(item: dict[str, Any], result: FetchResult, outcome: CheckOutcome) -> None:
    was_blocked = item.get("status") == "blocked"
    item["status"] = "blocked"
    if not was_blocked and not item.get("use_proxy"):
        outcome.ask_proxy.append(item)


def _fetch_with_proxy_fallback(item: dict[str, Any], fetcher: Fetcher, state: dict[str, Any]) -> FetchResult:
    result = fetcher.fetch(item["url"])
    if result.status == "blocked" and item.get("use_proxy"):
        result = fetcher.fetch_via_proxy(item["url"], state)
    return result


def check_price_item(item: dict[str, Any], fetcher: Fetcher, state: dict[str, Any], outcome: CheckOutcome) -> None:
    result = _fetch_with_proxy_fallback(item, fetcher, state)

    if result.status == "blocked":
        _handle_blocked(item, result, outcome)
        return
    if result.status == "needs_js":
        item["status"] = "needs_js"
        return
    if result.status == "failing":
        _record_failure(item, result.reason or "fetch failed", outcome)
        return

    extracted = extract_price(result.text or "", item.get("selector"))
    if extracted is None:
        item["status"] = "failing"
        outcome.ask_price.append(item)
        return

    if extracted.selector_used and not item.get("selector"):
        item["selector"] = extracted.selector_used

    item["fail_count"] = 0
    item["status"] = "ok"
    item["last_checked"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

    previous_price = item.get("last_price")
    new_price = extracted.price_cents
    item["currency"] = extracted.currency
    item["last_price"] = new_price

    history = item.setdefault("history", [])
    history.append({"d": _today(), "p": new_price})
    if len(history) > MAX_HISTORY:
        del history[: len(history) - MAX_HISTORY]

    if previous_price is None:
        return

    dropped = previous_price - new_price
    if dropped <= 0:
        return

    pct = dropped / previous_price * 100
    threshold_pct = 3.0
    threshold_abs = 200  # €2 in cents
    notify_drop = pct >= threshold_pct or dropped >= threshold_abs
    target = item.get("target_price")
    notify_target = target is not None and new_price <= target

    if notify_drop or notify_target:
        lines = [
            item["label"],
            f"{_format_price(previous_price, item['currency'])} → {_format_price(new_price, item['currency'])}  (−{pct:.0f}%)",
        ]
        if notify_target:
            lines.append(f"🎯 below your {_format_price(target, item['currency'])} target")
        lines.append(item["url"])
        outcome.events.append(CheckEvent(item, "price_drop", "\n".join(lines)))


def check_page_diff_item(item: dict[str, Any], fetcher: Fetcher, state: dict[str, Any], outcome: CheckOutcome) -> None:
    result = _fetch_with_proxy_fallback(item, fetcher, state)

    if result.status == "blocked":
        _handle_blocked(item, result, outcome)
        return
    if result.status == "needs_js":
        item["status"] = "needs_js"
        return
    if result.status == "failing":
        _record_failure(item, result.reason or "fetch failed", outcome)
        return

    cleaned = clean_page_text(result.text or "")
    new_hash = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()

    item["fail_count"] = 0
    item["status"] = "ok"
    item["last_checked"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

    previous_text = load_snapshot(item["id"])
    previous_hash = item.get("last_hash")

    if previous_hash is not None and new_hash != previous_hash and previous_text is not None:
        old_keywords = found_sale_keywords(previous_text)
        new_keywords = found_sale_keywords(cleaned)
        newly_appeared = new_keywords - old_keywords
        if newly_appeared:
            outcome.events.append(
                CheckEvent(
                    item,
                    "sale_detected",
                    f"🏷️ {item['label']}\nSale keywords appeared: {', '.join(sorted(newly_appeared))}\n{item['url']}",
                )
            )

    item["last_hash"] = new_hash
    save_snapshot(item["id"], cleaned)


def check_item(item: dict[str, Any], fetcher: Fetcher, state: dict[str, Any], outcome: CheckOutcome) -> None:
    if item.get("mode") == "page_diff":
        check_page_diff_item(item, fetcher, state, outcome)
    else:
        check_price_item(item, fetcher, state, outcome)
