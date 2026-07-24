"""Session-aware HTTP fetching: browser-like headers, robots.txt, proxy fallback."""
from __future__ import annotations

import random
import time
import urllib.robotparser
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

BASE_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-IE,en;q=0.9",
    # No "br": httpx can only auto-decompress Brotli if the optional `brotli`
    # package is installed, which isn't one of this project's four deps.
    # Advertising only gzip/deflate keeps servers from ever sending Brotli.
    "Accept-Encoding": "gzip, deflate",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

MONTHLY_PROXY_CAP = 900
NEEDS_JS_MARKERS = (
    "enable javascript",
    "checking your browser",
    "just a moment",
    "cf-browser-verification",
)
GARBLED_SAMPLE_SIZE = 2000
GARBLED_CONTROL_CHAR_RATIO = 0.05


def _looks_garbled(text: str) -> bool:
    """Catch responses that decoded to bytes rather than HTML — e.g. a
    compression scheme (Brotli) we advertised support for but can't actually
    decode. A real HTML page has a "<html"/"<!doctype" marker near the top and
    almost no control characters; raw compressed bytes have neither."""
    sample = text[:GARBLED_SAMPLE_SIZE]
    lowered = sample.lower()
    if "<html" in lowered or "<!doctype" in lowered or "<?xml" in lowered:
        return False
    control_chars = sum(1 for c in sample if ord(c) < 32 and c not in "\t\n\r")
    return bool(sample) and control_chars / len(sample) > GARBLED_CONTROL_CHAR_RATIO


@dataclass
class FetchResult:
    status: str  # "ok", "blocked", "needs_js", "failing"
    text: str | None = None
    reason: str | None = None


class Fetcher:
    def __init__(self, scraperapi_key: str | None = None) -> None:
        self.scraperapi_key = scraperapi_key
        self._primed_domains: set[str] = set()
        self._robots_cache: dict[str, urllib.robotparser.RobotFileParser] = {}
        self._client = httpx.Client(http2=True, follow_redirects=True, timeout=20, headers=BASE_HEADERS)

    def close(self) -> None:
        self._client.close()

    def _robots_allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        rp = self._robots_cache.get(origin)
        if rp is None:
            rp = urllib.robotparser.RobotFileParser()
            rp.set_url(f"{origin}/robots.txt")
            try:
                resp = self._client.get(f"{origin}/robots.txt", timeout=10)
                if resp.status_code == 200:
                    rp.parse(resp.text.splitlines())
                else:
                    rp.parse([])
            except httpx.HTTPError:
                rp.parse([])
            self._robots_cache[origin] = rp
        return rp.can_fetch(USER_AGENT, url)

    def _prime_session(self, url: str) -> None:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin in self._primed_domains:
            return
        self._primed_domains.add(origin)
        try:
            self._client.get(origin, timeout=20)
            time.sleep(random.uniform(1, 2))
        except httpx.HTTPError:
            pass

    def fetch(self, url: str) -> FetchResult:
        if not self._robots_allowed(url):
            return FetchResult(status="blocked", reason="disallowed by robots.txt")

        self._prime_session(url)
        time.sleep(random.uniform(2, 5))

        last_error: Exception | None = None
        for attempt in range(3):
            try:
                resp = self._client.get(url)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                return FetchResult(status="failing", reason=str(exc))

            if resp.status_code in (403, 429):
                return FetchResult(status="blocked", reason=f"HTTP {resp.status_code}")
            if resp.status_code >= 500:
                last_error = RuntimeError(f"HTTP {resp.status_code}")
                if attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                return FetchResult(status="failing", reason=f"HTTP {resp.status_code}")
            if resp.status_code >= 400:
                return FetchResult(status="failing", reason=f"HTTP {resp.status_code}")

            text = resp.text
            if len(text.strip()) < 200 or any(marker in text.lower() for marker in NEEDS_JS_MARKERS):
                return FetchResult(status="needs_js", reason="empty body or challenge page")
            if _looks_garbled(text):
                return FetchResult(status="failing", reason="response didn't decode to HTML (possible encoding/compression mismatch)")

            return FetchResult(status="ok", text=text)

        return FetchResult(status="failing", reason=str(last_error))

    def fetch_via_proxy(self, url: str, state: dict) -> FetchResult:
        if not self.scraperapi_key:
            return FetchResult(status="blocked", reason="no SCRAPERAPI_KEY configured")
        if not self._robots_allowed(url):
            return FetchResult(status="blocked", reason="disallowed by robots.txt")

        month = time.strftime("%Y-%m")
        if state.get("proxy_month") != month:
            state["proxy_month"] = month
            state["proxy_requests_this_month"] = 0
        if state["proxy_requests_this_month"] >= MONTHLY_PROXY_CAP:
            return FetchResult(status="blocked", reason="monthly proxy quota reached")

        try:
            resp = self._client.get(
                "https://api.scraperapi.com/",
                params={"api_key": self.scraperapi_key, "url": url},
                timeout=60,
            )
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            return FetchResult(status="failing", reason=str(exc))

        state["proxy_requests_this_month"] += 1

        if resp.status_code in (403, 429):
            return FetchResult(status="blocked", reason=f"HTTP {resp.status_code} via proxy")
        if resp.status_code >= 400:
            return FetchResult(status="failing", reason=f"HTTP {resp.status_code} via proxy")

        text = resp.text
        if len(text.strip()) < 200:
            return FetchResult(status="needs_js", reason="empty body via proxy")
        if _looks_garbled(text):
            return FetchResult(status="failing", reason="response didn't decode to HTML via proxy")

        return FetchResult(status="ok", text=text)
