"""Telegram command parsing, dispatch, and the conversational (pending) state machine."""
from __future__ import annotations

import datetime
import re
from typing import Any

from selectolax.parser import HTMLParser

from src.extract import parse_price
from src.fetch import Fetcher
from src.handlers import (
    handle_add,
    handle_chart,
    handle_check,
    handle_list,
    handle_pause_resume,
    handle_remove,
    handle_status,
    handle_target,
    handle_watch,
)
from src.item_helpers import format_price, now_iso, today
from src.store import find_item
from src.telegram import TelegramClient

PENDING_EXPIRY_HOURS = 48

HELP_TEXT = """Commands:
/add <url> - watch a product's price
/watch <url> [label=...] - watch a page for sale keywords
/list - show all watched items
/remove <id> - stop watching an item
/pause <id> / /resume <id> - toggle an item
/target <id> <price> - set target price (or "none" to clear)
/chart <id> - send price history chart
/check [id] - force a check now (applies on next scheduled run)
/status - summary of last run
/help - this message"""


def _pending_expired(pending: dict[str, Any]) -> bool:
    created = datetime.datetime.fromisoformat(pending["created"])
    age = datetime.datetime.now(datetime.timezone.utc) - created
    return age > datetime.timedelta(hours=PENDING_EXPIRY_HOURS)


def _derive_selector(html: str, literal_price: str) -> str | None:
    """Match by parsed value, not literal text — the page rarely renders the
    currency symbol and decimals exactly as the user typed them."""
    target_cents = parse_price(literal_price)
    if target_cents is None:
        return None
    tree = HTMLParser(html)
    for node in tree.css("*"):
        text = node.text(deep=False) or ""
        if not text.strip() or parse_price(text) != target_cents:
            continue
        classes = node.attributes.get("class")
        if classes:
            return f"{node.tag}.{classes.split()[0]}"
        return node.tag
    return None


def _resolve_pending_target(item: dict[str, Any], text: str, watchlist: dict[str, Any], state: dict[str, Any], tg: TelegramClient) -> bool:
    if not (text.strip().lower() == "none" or parse_price(text) is not None):
        return False
    handle_target(item["id"], text, watchlist, tg)
    state["pending"] = None
    tg.send_message(f"✅ Watching #{item['id']} · {item['label']}")
    return True


def _resolve_pending_proxy_confirm(item: dict[str, Any], text: str, state: dict[str, Any], tg: TelegramClient) -> bool:
    answer = text.strip().lower()
    if answer not in ("yes", "y", "no", "n"):
        return False
    if answer in ("yes", "y"):
        item["use_proxy"] = True
        tg.send_message(f"✅ #{item['id']} will use the proxy on the next run (quota permitting).")
    else:
        tg.send_message(f"OK, leaving #{item['id']} blocked without proxy.")
    state["pending"] = None
    return True


def _resolve_pending_price(item: dict[str, Any], text: str, state: dict[str, Any], fetcher: Fetcher, tg: TelegramClient) -> bool:
    result = fetcher.fetch(item["url"])
    if result.status != "ok" or result.text is None:
        tg.send_message("Couldn't refetch the page to confirm that price. Try /check again shortly.")
        return True
    cents = parse_price(text)
    if cents is None:
        tg.send_message(f"Couldn't parse '{text}' as a price. Try again.")
        return True
    item["selector"] = _derive_selector(result.text, text.strip())
    item["last_price"] = cents
    item["history"] = [{"d": today(), "p": cents}]
    item["status"] = "ok"
    state["pending"] = {"item_id": item["id"], "awaiting": "target", "created": now_iso()}
    tg.send_message(f"Got it — {format_price(cents, item.get('currency', 'EUR'))}.\nSend a target price, or \"none\" to just track drops.")
    return True


def _resolve_pending(text: str, watchlist: dict[str, Any], state: dict[str, Any], fetcher: Fetcher, tg: TelegramClient) -> bool:
    pending = state.get("pending")
    if not pending:
        return False
    if _pending_expired(pending):
        state["pending"] = None
        return False

    item = find_item(watchlist, pending["item_id"])
    if item is None:
        state["pending"] = None
        return False

    if pending["awaiting"] == "target":
        return _resolve_pending_target(item, text, watchlist, state, tg)
    if pending["awaiting"] == "proxy_confirm":
        return _resolve_pending_proxy_confirm(item, text, state, tg)
    if pending["awaiting"] == "price":
        return _resolve_pending_price(item, text, state, fetcher, tg)
    return False


def _parse_command(text: str) -> tuple[str, str]:
    parts = text.strip().split(maxsplit=1)
    cmd = parts[0].lower()
    rest = parts[1].strip() if len(parts) > 1 else ""
    return cmd, rest


def dispatch(text: str, watchlist: dict[str, Any], state: dict[str, Any], fetcher: Fetcher, tg: TelegramClient) -> None:
    text = text.strip()
    if not text:
        return

    if not text.startswith("/") and _resolve_pending(text, watchlist, state, fetcher, tg):
        return

    if not text.startswith("/"):
        return

    cmd, rest = _parse_command(text)

    if cmd == "/add":
        if not rest:
            tg.send_message("Usage: /add <url>")
            return
        handle_add(rest, watchlist, state, fetcher, tg)
    elif cmd == "/watch":
        match = re.match(r"(\S+)(?:\s+label=(.*))?$", rest)
        if not match or not match.group(1):
            tg.send_message("Usage: /watch <url> [label=...]")
            return
        handle_watch(match.group(1), match.group(2), watchlist, tg)
    elif cmd == "/list":
        handle_list(watchlist, tg)
    elif cmd == "/remove":
        if not rest.isdigit():
            tg.send_message("Usage: /remove <id>")
            return
        handle_remove(int(rest), watchlist, tg)
    elif cmd == "/pause":
        if not rest.isdigit():
            tg.send_message("Usage: /pause <id>")
            return
        handle_pause_resume(int(rest), True, watchlist, tg)
    elif cmd == "/resume":
        if not rest.isdigit():
            tg.send_message("Usage: /resume <id>")
            return
        handle_pause_resume(int(rest), False, watchlist, tg)
    elif cmd == "/target":
        parts = rest.split(maxsplit=1)
        if len(parts) != 2 or not parts[0].isdigit():
            tg.send_message("Usage: /target <id> <price|none>")
            return
        handle_target(int(parts[0]), parts[1], watchlist, tg)
    elif cmd == "/chart":
        if not rest.isdigit():
            tg.send_message("Usage: /chart <id>")
            return
        handle_chart(int(rest), watchlist, tg)
    elif cmd == "/check":
        item_id = int(rest) if rest.isdigit() else None
        handle_check(item_id, watchlist, state, fetcher, tg)
    elif cmd == "/status":
        handle_status(watchlist, state, tg)
    elif cmd == "/help":
        tg.send_message(HELP_TEXT)
    else:
        tg.send_message("Unknown command. /help for the list.")
