"""Price extraction ladder: JSON-LD -> microdata -> OG meta -> selector -> LLM -> ask user."""
from __future__ import annotations

import json

from selectolax.parser import HTMLParser

from src.extract_types import ExtractedPrice
from src.llm_fallback import extract_llm
from src.price_string import parse_price

__all__ = [
    "ExtractedPrice",
    "extract_json_ld",
    "extract_llm",
    "extract_microdata",
    "extract_opengraph",
    "extract_price",
    "extract_selector",
    "parse_price",
]


def _walk_json_ld_node(node: object) -> tuple[str, str] | None:
    if isinstance(node, list):
        for item in node:
            result = _walk_json_ld_node(item)
            if result:
                return result
        return None
    if not isinstance(node, dict):
        return None

    if "@graph" in node:
        result = _walk_json_ld_node(node["@graph"])
        if result:
            return result

    type_val = node.get("@type", "")
    types = type_val if isinstance(type_val, list) else [type_val]
    if any(str(t).lower() == "product" for t in types):
        offers = node.get("offers")
        offer_list = offers if isinstance(offers, list) else [offers] if offers else []
        for offer in offer_list:
            if not isinstance(offer, dict):
                continue
            if offer.get("price") is not None:
                return str(offer["price"]), offer.get("priceCurrency", "EUR")
            # Some schema plugins (e.g. WooCommerce) nest the price under
            # priceSpecification instead of directly on the offer, and use it to
            # carry both the current price and a strikethrough "list" price.
            spec = offer.get("priceSpecification")
            spec_list = spec if isinstance(spec, list) else [spec] if spec else []
            for entry in spec_list:
                if isinstance(entry, dict) and entry.get("price") is not None and not entry.get("priceType"):
                    return str(entry["price"]), entry.get("priceCurrency", "EUR")

    for value in node.values():
        if isinstance(value, (dict, list)):
            result = _walk_json_ld_node(value)
            if result:
                return result
    return None


def extract_json_ld(html: str) -> ExtractedPrice | None:
    tree = HTMLParser(html)
    for script in tree.css("script[type='application/ld+json']"):
        text = script.text(deep=True)
        if not text:
            continue
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue
        result = _walk_json_ld_node(data)
        if result:
            price_str, currency = result
            cents = parse_price(price_str)
            if cents is not None:
                return ExtractedPrice(cents, currency, None)
    return None


def extract_microdata(html: str) -> ExtractedPrice | None:
    tree = HTMLParser(html)
    node = tree.css_first("[itemprop='price']")
    if node is None:
        return None
    content = node.attributes.get("content") or node.text(deep=True)
    cents = parse_price(content or "")
    if cents is None:
        return None
    currency_node = tree.css_first("[itemprop='priceCurrency']")
    currency = "EUR"
    if currency_node is not None:
        currency = currency_node.attributes.get("content") or currency_node.text(deep=True) or "EUR"
    return ExtractedPrice(cents, currency, "[itemprop='price']")


def extract_opengraph(html: str) -> ExtractedPrice | None:
    tree = HTMLParser(html)
    amount_node = tree.css_first("meta[property='product:price:amount']")
    if amount_node is None:
        return None
    amount = amount_node.attributes.get("content")
    cents = parse_price(amount or "")
    if cents is None:
        return None
    currency_node = tree.css_first("meta[property='product:price:currency']")
    currency = (currency_node.attributes.get("content") if currency_node is not None else None) or "EUR"
    return ExtractedPrice(cents, currency, "meta[property='product:price:amount']")


def extract_selector(html: str, selector: str) -> ExtractedPrice | None:
    tree = HTMLParser(html)
    node = tree.css_first(selector)
    if node is None:
        return None
    cents = parse_price(node.text(deep=True) or "")
    if cents is None:
        return None
    return ExtractedPrice(cents, "EUR", selector)


def extract_price(html: str, item_selector: str | None = None, api_key: str | None = None) -> ExtractedPrice | None:
    for extractor in (extract_json_ld, extract_microdata, extract_opengraph):
        result = extractor(html)
        if result is not None:
            return result

    if item_selector:
        result = extract_selector(html, item_selector)
        if result is not None:
            return result

    result = extract_llm(html, api_key=api_key)
    if result is not None:
        return result

    return None
