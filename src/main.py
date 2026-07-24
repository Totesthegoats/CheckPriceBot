"""Entrypoint: drain Telegram commands, run checks (full mode only), notify, persist state."""
from __future__ import annotations

import argparse
import datetime
import os

from src.charts import render_chart, should_send_auto_chart
from src.check import CheckEvent, CheckOutcome, check_item
from src.commands import dispatch
from src.fetch import Fetcher
from src.handlers import prompt_proxy_confirm
from src.store import load_state, load_watchlist, save_state, save_watchlist
from src.telegram import TelegramClient

NOTIFY_INLINE_LIMIT = 5


def drain_commands(watchlist: dict, state: dict, fetcher: Fetcher, tg: TelegramClient) -> None:
    allowed = set(tg.chat_ids)
    while True:
        updates = tg.get_updates(offset=state["telegram_offset"], timeout=0)
        if not updates:
            break
        for update in updates:
            state["telegram_offset"] = update["update_id"] + 1
            message = update.get("message")
            if not message:
                continue
            sender_chat_id = str(message.get("chat", {}).get("id"))
            if sender_chat_id not in allowed:
                continue
            text = message.get("text")
            if not text:
                continue
            tg.chat_id = sender_chat_id  # reply to whoever actually sent this
            dispatch(text, watchlist, state, fetcher, tg)


def run_full_check(watchlist: dict, state: dict, fetcher: Fetcher, tg: TelegramClient) -> None:
    outcome = CheckOutcome()
    checked = 0
    for item in watchlist["items"]:
        if item.get("paused"):
            continue
        checked += 1
        try:
            check_item(item, fetcher, state, outcome)
        except Exception as exc:  # noqa: BLE001 - never let one bad item abort the run
            item["fail_count"] = item.get("fail_count", 0) + 1
            item["status"] = "failing"
            outcome.events.append(CheckEvent(item, "warning", f"⚠️ {item['label']} raised an error: {exc}"))

    blocked = sum(1 for i in watchlist["items"] if i.get("status") == "blocked")
    failing = sum(1 for i in watchlist["items"] if i.get("status") == "failing")

    if outcome.events:
        messages = [e.message for e in outcome.events]
        if len(messages) <= NOTIFY_INLINE_LIMIT:
            body = "\n\n".join(messages)
        else:
            summary = f"{len(messages)} events this run:"
            per_item = "\n".join(f"- {e.item['label']}" for e in outcome.events)
            body = f"{summary}\n{per_item}"
        tail = f"\n\n{checked} checked · {blocked} blocked · {failing} failing"
        tg.broadcast(body + tail)

    for item in outcome.ask_proxy:
        prompt_proxy_confirm(item, state, tg)
        break  # one pending slot at a time

    for item in outcome.ask_price:
        if state.get("pending") is None:
            state["pending"] = {
                "item_id": item["id"],
                "awaiting": "price",
                "created": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }
            tg.broadcast(
                f"Couldn't find a price for {item['label']}. Reply with the price exactly as shown on the page."
            )
            break

    for item in watchlist["items"]:
        if should_send_auto_chart(item):
            path = render_chart(item)
            tg.broadcast_photo(path, caption=item["label"])
            item["last_chart_sent"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            os.remove(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["full", "drain"], required=True)
    args = parser.parse_args()

    watchlist = load_watchlist()
    state = load_state()
    tg = TelegramClient()
    fetcher = Fetcher(scraperapi_key=os.environ.get("SCRAPERAPI_KEY"))

    try:
        drain_commands(watchlist, state, fetcher, tg)
        tg.chat_id = tg.chat_ids[0]  # drain may have pointed this at a specific sender
        if args.mode == "full":
            run_full_check(watchlist, state, fetcher, tg)
    finally:
        fetcher.close()
        state["last_run"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        save_watchlist(watchlist)
        save_state(state)


if __name__ == "__main__":
    main()
