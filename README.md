# Sale Monitor

A Telegram-controlled price/sale watcher that runs entirely on GitHub Actions. No servers, no cloud costs — `watchlist.json` and `state.json` are committed back to the repo by the workflow.

## Setup

### 1. Create the bot

Message [@BotFather](https://t.me/BotFather) on Telegram, send `/newbot`, follow the prompts, and copy the token it gives you.

### 2. Get your chat id

Send any message to your new bot, then open this URL in a browser (with your token):

```
https://api.telegram.org/bot<TOKEN>/getUpdates
```

Find `message.chat.id` in the JSON response — that's your `TELEGRAM_CHAT_ID`.

### 3. Add repo secrets

In **Settings → Secrets and variables → Actions**, add:

| Secret | Required | Purpose |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | yes | from BotFather |
| `TELEGRAM_CHAT_ID` | yes | from step 2 — the bot ignores every other chat |
| `ANTHROPIC_API_KEY` | no | enables the LLM price-extraction fallback |
| `SCRAPERAPI_KEY` | no | enables the opt-in proxy fallback for blocked sites |

### 4. Enable Actions and let it run

The workflow runs a full scrape once daily and a lightweight command drain three more times a day, so Telegram commands don't sit unacknowledged near Telegram's 24-hour `getUpdates` expiry. See `.github/workflows/monitor.yml`.

## Commands

Send these to your bot (see `src/commands.py:HELP_TEXT` / `/help`):

```
/add <url>              watch a product's price
/watch <url> [label=...] watch a page for sale keywords
/list                    show all watched items
/remove <id>             stop watching an item
/pause <id> / /resume <id>
/target <id> <price>     set target price ("none" to clear)
/chart <id>              send price history chart
/check [id]              force a check now
/status                  summary of last run
```

`/add` is conversational: it fetches the page immediately, reports what it found, and asks for a target price. If it can't find a price automatically, it'll ask you to paste the price as shown on the page and derive a CSS selector from that.

## Important caveats

- **Scheduling is best-effort.** GitHub delays scheduled workflows under load — sometimes 30+ minutes. Fine for sale monitoring, useless for limited-stock drops.
- **`/check` doesn't run instantly.** A command sent via Telegram is only *applied* at the next scheduled run (full or drain). For an on-demand check right now, trigger the workflow manually via `workflow_dispatch` — e.g. from the GitHub mobile app — with `mode: full`.
- **Respect each retailer's ToS.** Polling a product page once a day is unremarkable, but some sites prohibit automated access outright, and sites behind heavy anti-bot infrastructure (Cloudflare Bot Management, DataDome, PerimeterX, Akamai) will 403 you regardless of politeness. Expect partial coverage — this bot does not attempt to defeat those systems. Smaller and mid-size retailers usually work fine with plain `httpx`; the heavy defenses cluster at the big names.
- **Triage before committing to a watchlist.** Run each candidate URL through `/add` or `/watch` once and check `/status` before relying on it. `status` will tell you `ok`, `blocked` (bot detection or robots.txt), `needs_js` (client-rendered price, out of scope for this bot), or `failing` (transient errors).
- **`page_diff` mode only catches multi-day sales.** At once-a-day cadence it will miss anything shorter — that's an accepted tradeoff, not a bug.
- **The proxy fallback is opt-in per item, quota-capped, and still respects `robots.txt`.** When an item is blocked, the bot asks on Telegram whether to retry it via ScraperAPI; it only sets `use_proxy` on a "yes", and stops proxying (with a Telegram warning) once the monthly request cap is hit.

## Architecture notes

- All prices are stored as integer minor units (cents) to avoid float drift.
- `state.json.last_run` is written unconditionally on every run, so there's always a commit — GitHub disables scheduled workflows after 60 days of repo inactivity, and an all-paused watchlist would otherwise never push.
- Page snapshots for `page_diff` items are gzipped and stored under `snapshots/` rather than inline in `watchlist.json`, so the watchlist file stays readable.

## Local development

```
pip install -r requirements.txt
pytest
ruff check src tests
```

Tests use saved HTML fixtures and fakes for Telegram/fetch — nothing hits live retail sites.
