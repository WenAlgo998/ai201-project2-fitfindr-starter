"""
Tool-level tests for FitFindr.

Each of the three tools has at least one test for its failure mode:
  - search_listings  → returns [] (no exception) when nothing matches
  - suggest_outfit   → returns non-empty advice (no crash) on an empty wardrobe
  - create_fit_card  → returns an error-message string (no crash) on empty outfit

The two LLM-backed tools call Groq over the network, so those tests are skipped
when GROQ_API_KEY is not set (e.g. in CI without a key). The deterministic,
network-free tests — all of search_listings plus the empty-outfit guard — always run.

Run with:  pytest tests/
"""

import os

import pytest

from tools import search_listings, suggest_outfit, create_fit_card, compare_price
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe, load_listings
from agent import _search_with_fallback

needs_groq = pytest.mark.skipif(
    not os.environ.get("GROQ_API_KEY"),
    reason="GROQ_API_KEY not set — skipping live LLM test",
)


# ── search_listings (pure Python, deterministic) ───────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    # Failure mode: nothing matches → empty list, never an exception.
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=40)
    assert all(item["price"] <= 40 for item in results)


def test_search_size_filter_substring():
    # "m" should match listings whose size contains it (e.g. "M", "S/M", "M/L").
    results = search_listings("top", size="M", max_price=None)
    assert all("m" in item["size"].lower() for item in results)


def test_search_sorted_by_relevance():
    # More keyword overlap should rank at or above less overlap.
    results = search_listings("vintage denim jacket", size=None, max_price=None)
    assert len(results) >= 2
    # The top result should mention at least one query keyword.
    top = results[0]
    haystack = (top["title"] + top["description"] + " ".join(top["style_tags"])).lower()
    assert any(kw in haystack for kw in ("vintage", "denim", "jacket"))


def test_search_returns_full_listing_fields():
    results = search_listings("vintage tee", size=None, max_price=None)
    expected = {
        "id", "title", "description", "category", "style_tags",
        "size", "condition", "price", "colors", "brand", "platform",
    }
    assert expected.issubset(results[0].keys())


# ── create_fit_card failure mode (network-free guard) ───────────────────────────

def test_fit_card_empty_outfit_returns_message():
    # Failure mode: empty/whitespace outfit → descriptive string, no crash.
    item = load_listings()[0]
    result = create_fit_card("", item)
    assert isinstance(result, str)
    assert result.strip() != ""
    assert "outfit" in result.lower()


def test_fit_card_whitespace_outfit_returns_message():
    item = load_listings()[0]
    result = create_fit_card("   \n  ", item)
    assert isinstance(result, str)
    assert result.strip() != ""


# ── LLM-backed tools (live Groq calls; skipped without a key) ───────────────────

@needs_groq
def test_suggest_outfit_empty_wardrobe_does_not_crash():
    # Failure mode: empty wardrobe → non-empty general advice, no exception.
    item = load_listings()[0]
    result = suggest_outfit(item, get_empty_wardrobe())
    assert isinstance(result, str)
    assert result.strip() != ""


@needs_groq
def test_suggest_outfit_with_wardrobe_returns_text():
    item = load_listings()[0]
    result = suggest_outfit(item, get_example_wardrobe())
    assert isinstance(result, str)
    assert result.strip() != ""


@needs_groq
def test_fit_card_varies_on_repeat():
    # Higher temperature should make repeated captions differ.
    item = load_listings()[0]
    outfit = "Pair it with baggy dark-wash jeans and chunky white sneakers."
    a = create_fit_card(outfit, item)
    b = create_fit_card(outfit, item)
    assert a != b


# ── Stretch: compare_price (pure Python) ────────────────────────────────────────

def test_compare_price_returns_reasoned_string():
    item = load_listings()[0]
    result = compare_price(item)
    assert isinstance(result, str)
    # Mentions the price and references comparable items (reasoning).
    assert "$" in result
    assert "comparable" in result.lower() or "compare" in result.lower()


def test_compare_price_verdict_matches_relative_price():
    listings = load_listings()
    tops = [l for l in listings if l["category"] == "tops"]
    cheapest = min(tops, key=lambda l: l["price"])
    priciest = max(tops, key=lambda l: l["price"])
    assert "great deal" in compare_price(cheapest).lower()
    assert "a bit high" in compare_price(priciest).lower()


# ── Stretch: retry-with-fallback search (pure Python) ───────────────────────────

def test_fallback_loosens_price_when_too_low():
    # Tees exist, but none under $5 — fallback should drop the price limit.
    parsed = {"description": "vintage graphic tee", "size": None, "max_price": 5.0}
    results, note = _search_with_fallback(parsed)
    assert len(results) > 0
    assert note is not None and "loosened" in note.lower()


def test_fallback_drops_size_when_unmatched():
    # Band tees are size L; size XS won't match — fallback should drop size.
    parsed = {"description": "band tee", "size": "XS", "max_price": None}
    results, note = _search_with_fallback(parsed)
    assert len(results) > 0
    assert note is not None and "size" in note.lower()


def test_fallback_no_note_when_first_search_succeeds():
    parsed = {"description": "vintage tee", "size": None, "max_price": None}
    results, note = _search_with_fallback(parsed)
    assert len(results) > 0
    assert note is None


def test_fallback_total_failure_returns_empty():
    # No "designer ballgown" exists at any price/size.
    parsed = {"description": "designer ballgown", "size": "XXS", "max_price": 5.0}
    results, note = _search_with_fallback(parsed)
    assert results == []
    assert note is None
