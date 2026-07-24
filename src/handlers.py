"""Handlers for each Telegram command (excluding the conversational pending flow)."""
from __future__ import annotations

from typing import Any

from selectolax.parser import HTMLParser

from src.charts import render_chart
from src.check import CheckOutcome, check_item
from src.extract import extract_price, parse_price
from src.fetch import Fetcher
from src.item_helpers import format_price, new_item, now_iso, today
from src.store import find_item, next_item_id, remove_item
from src.telegram import TelegramClient


def _page_title(html: str) -> str | None:
    tree = HTMLParser(html)
    node = tree.css_first("title")
    return node.text(deep=True).strip() if node is not None else None


def handle_add(url: str, watchlist: dict[str, Any], state: dict[str, Any], fetcher: Fetcher, tg: TelegramClient) -> None:
    result = fetcher.fetch(url)
    item_id = next_item_id(watchlist)
    item = new_item(item_id, "price", url, url)

    if result.status != "ok":
        item["status"] = result.status
        watchlist["items"].append(item)
        tg.send_message(f"Added #{item_id} but couldn't fetch it yet ({result.reason}). It'll retry on the next run.")
        return

    title = _page_title(result.text or "")
    if title:
        item["label"] = title

    extracted = extract_price(result.text or "", None)
    if extracted is None:
        watchlist["items"].append(item)
        state["pending"] = {"item_id": item_id, "awaiting": "price", "created": now_iso()}
        tg.send_message(
            f"Added #{item_id} · {item['label']}\n"
            "Couldn't find a price on that page. Reply with the price exactly as shown on the page."
        )
        return

    item["last_price"] = extracted.price_cents
    item["currency"] = extracted.currency
    item["selector"] = extracted.selector_used
    item["history"] = [{"d": today(), "p": extracted.price_cents}]
    watchlist["items"].append(item)

    state["pending"] = {"item_id": item_id, "awaiting": "target", "created": now_iso()}
    tg.send_message(
        f"Found: {item['label']} — {format_price(extracted.price_cents, extracted.currency)}\n"
        'Send a target price, or "none" to just track drops.'
    )


def handle_watch(url: str, label: str | None, watchlist: dict[str, Any], tg: TelegramClient) -> None:
    item_id = next_item_id(watchlist)
    item = new_item(item_id, "page_diff", url, label or url)
    watchlist["items"].append(item)
    tg.send_message(f"✅ Watching #{item_id} for sales · {item['label']}")


def handle_list(watchlist: dict[str, Any], tg: TelegramClient) -> None:
    items = watchlist["items"]
    if not items:
        tg.send_message("Watchlist is empty. Use /add <url> or /watch <url>.")
        return
    lines = []
    for item in items:
        state_flags = []
        if item.get("paused"):
            state_flags.append("paused")
        state_flags.append(item.get("status", "ok"))
        flags = ", ".join(state_flags)
        if item.get("mode") == "page_diff":
            lines.append(f"#{item['id']} {item['label']} · page watch · {flags}")
        else:
            price = format_price(item["last_price"], item.get("currency", "EUR")) if item.get("last_price") is not None else "?"
            target = (
                format_price(item["target_price"], item.get("currency", "EUR"))
                if item.get("target_price") is not None
                else "none"
            )
            lines.append(f"#{item['id']} {item['label']} · {price} (target {target}) · {flags}")
    tg.send_message("\n".join(lines))


def handle_remove(item_id: int, watchlist: dict[str, Any], tg: TelegramClient) -> None:
    if remove_item(watchlist, item_id):
        tg.send_message(f"Removed #{item_id}.")
    else:
        tg.send_message(f"No item #{item_id}.")


def handle_pause_resume(item_id: int, paused: bool, watchlist: dict[str, Any], tg: TelegramClient) -> None:
    item = find_item(watchlist, item_id)
    if item is None:
        tg.send_message(f"No item #{item_id}.")
        return
    item["paused"] = paused
    tg.send_message(f"{'Paused' if paused else 'Resumed'} #{item_id} · {item['label']}")


def handle_target(item_id: int, value: str, watchlist: dict[str, Any], tg: TelegramClient) -> None:
    item = find_item(watchlist, item_id)
    if item is None:
        tg.send_message(f"No item #{item_id}.")
        return
    if value.strip().lower() == "none":
        item["target_price"] = None
        tg.send_message(f"Cleared target for #{item_id}.")
        return
    cents = parse_price(value)
    if cents is None:
        tg.send_message(f"Couldn't parse '{value}' as a price.")
        return
    item["target_price"] = cents
    tg.send_message(f"Target for #{item_id} set to {format_price(cents, item.get('currency', 'EUR'))}.")


def handle_chart(item_id: int, watchlist: dict[str, Any], tg: TelegramClient) -> None:
    item = find_item(watchlist, item_id)
    if item is None:
        tg.send_message(f"No item #{item_id}.")
        return
    if len(item.get("history", [])) < 2:
        tg.send_message(f"Not enough history for #{item_id} yet.")
        return
    path = render_chart(item)
    tg.send_photo(path, caption=item["label"])
    item["last_chart_sent"] = now_iso()


def handle_check(item_id: int | None, watchlist: dict[str, Any], state: dict[str, Any], fetcher: Fetcher, tg: TelegramClient) -> None:
    outcome = CheckOutcome()
    targets = watchlist["items"] if item_id is None else [i for i in watchlist["items"] if i["id"] == item_id]
    if not targets:
        tg.send_message(f"No item #{item_id}.")
        return
    for item in targets:
        check_item(item, fetcher, state, outcome)
    if outcome.events:
        tg.send_message("\n\n".join(e.message for e in outcome.events))
    else:
        tg.send_message(f"Checked {len(targets)} item(s). No changes to report.")


def handle_status(watchlist: dict[str, Any], state: dict[str, Any], tg: TelegramClient) -> None:
    items = watchlist["items"]
    ok = sum(1 for i in items if i.get("status") == "ok")
    blocked = sum(1 for i in items if i.get("status") == "blocked")
    failing = sum(1 for i in items if i.get("status") == "failing")
    needs_js = sum(1 for i in items if i.get("status") == "needs_js")
    last_run = state.get("last_run") or "never"
    tg.send_message(f"{ok} ok · {blocked} blocked · {failing} failing · {needs_js} needs JS\nLast run: {last_run}")


def prompt_proxy_confirm(item: dict[str, Any], state: dict[str, Any], tg: TelegramClient) -> None:
    if state.get("pending"):
        return
    state["pending"] = {"item_id": item["id"], "awaiting": "proxy_confirm", "created": now_iso()}
    tg.broadcast(
        f"🚫 #{item['id']} · {item['label']} is blocked.\n"
        "Retry it through the proxy (uses your ScraperAPI quota)? Reply yes or no."
    )
