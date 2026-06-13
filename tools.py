"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os
import re

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()

# LLM model used by the two generative tools.
_MODEL = "llama-3.3-70b-versatile"

# Tiny stopword set so common connective words in a description don't inflate
# relevance scores in search_listings.
_STOPWORDS = {
    "a", "an", "the", "for", "with", "and", "or", "in", "to", "of", "my",
    "under", "size", "i", "looking", "want", "need", "some",
}


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform

    TODO:
        1. Load all listings with load_listings().
        2. Filter by max_price and size (if provided).
        3. Score each remaining listing by keyword overlap with `description`.
        4. Drop any listings with a score of 0 (no relevant matches).
        5. Sort by score, highest first, and return the listing dicts.

    Before writing code, fill in the Tool 1 section of planning.md.
    """
    listings = load_listings()

    # 1. Apply the hard filters (price ceiling, size) first.
    candidates = []
    for item in listings:
        if max_price is not None and item["price"] > max_price:
            continue
        if size is not None and size.strip().lower() not in item["size"].lower():
            continue
        candidates.append(item)

    # 2. Score each candidate by keyword overlap between the description and
    #    the item's title + description + style_tags.
    query_tokens = {
        tok
        for tok in re.findall(r"[a-z0-9]+", description.lower())
        if tok not in _STOPWORDS and len(tok) >= 3
    }

    scored = []
    for item in candidates:
        haystack = " ".join(
            [item["title"], item["description"], " ".join(item["style_tags"])]
        ).lower()
        score = sum(1 for tok in query_tokens if tok in haystack)
        if score > 0:
            scored.append((score, item))

    # 3. Sort by score, highest first (stable — ties keep dataset order).
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.

    TODO:
        1. Check whether wardrobe['items'] is empty.
        2. If empty: call the LLM with a prompt for general styling ideas
           (what kinds of items pair well, what vibe it suits, etc.).
        3. If not empty: format the wardrobe items into a prompt and ask
           the LLM to suggest specific outfit combinations using the new item
           and named pieces from the wardrobe.
        4. Return the LLM's response as a string.

    Before writing code, fill in the Tool 2 section of planning.md.
    """
    client = _get_groq_client()

    item_desc = (
        f"{new_item['title']} "
        f"(category: {new_item['category']}, "
        f"colors: {', '.join(new_item['colors'])}, "
        f"style: {', '.join(new_item['style_tags'])})"
    )

    items = (wardrobe or {}).get("items", [])

    if not items:
        # Empty-wardrobe branch: no owned pieces to name, so give general
        # styling advice for the item on its own.
        prompt = (
            "You are a thoughtful personal stylist for secondhand fashion.\n"
            f"A shopper is considering this thrifted item:\n  {item_desc}\n\n"
            "They have not entered any wardrobe yet. In 2-3 sentences, give "
            "general styling advice for this piece: what kinds of items pair "
            "well with it, what colors complement it, and what overall vibe or "
            "aesthetic it suits. Do not invent specific items they own."
        )
    else:
        # Format the wardrobe so the model can name specific owned pieces.
        wardrobe_lines = "\n".join(
            f"  - {it['name']} (category: {it['category']}, "
            f"colors: {', '.join(it['colors'])}, "
            f"style: {', '.join(it['style_tags'])})"
            for it in items
        )
        prompt = (
            "You are a thoughtful personal stylist for secondhand fashion.\n"
            f"A shopper is considering this thrifted item:\n  {item_desc}\n\n"
            f"Here is their existing wardrobe:\n{wardrobe_lines}\n\n"
            "Suggest 1-2 complete outfits that pair the new item with specific "
            "pieces from their wardrobe. Refer to the owned pieces by name. "
            "Keep it to 2-4 sentences, concrete, and explain the vibe. Only use "
            "pieces from the wardrobe listed above."
        )

    response = client.chat.completions.create(
        model=_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=300,
    )
    return response.choices[0].message.content.strip()


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)

    TODO:
        1. Guard against an empty or whitespace-only outfit string.
        2. Build a prompt that gives the LLM the item details and the outfit,
           and asks for a caption matching the style guidelines above.
        3. Call the LLM and return the response.

    Before writing code, fill in the Tool 3 section of planning.md.
    """
    # Guard: no outfit to caption — return a message, don't crash.
    if not outfit or not outfit.strip():
        return (
            "Can't write a fit card without an outfit suggestion — "
            "try styling the item first."
        )

    brand = new_item.get("brand")
    item_desc = (
        f"{new_item['title']}"
        + (f" by {brand}" if brand else "")
        + f", ${new_item['price']:.0f}, from {new_item['platform']}"
    )

    prompt = (
        "Write a short, casual social-media caption (Instagram/TikTok OOTD "
        "style) for a secondhand fashion find. It should:\n"
        "- Feel authentic and a little playful — NOT a product description.\n"
        "- Mention the item name, its price, and the platform naturally, once each.\n"
        "- Capture the outfit's vibe in specific terms.\n"
        "- Be 2-4 sentences. Emojis are welcome but optional.\n\n"
        f"Item: {item_desc}\n"
        f"Outfit: {outfit}\n\n"
        "Caption:"
    )

    client = _get_groq_client()
    response = client.chat.completions.create(
        model=_MODEL,
        messages=[{"role": "user", "content": prompt}],
        # Higher temperature so repeated calls on the same input vary.
        temperature=1.1,
        max_tokens=200,
    )
    return response.choices[0].message.content.strip()
