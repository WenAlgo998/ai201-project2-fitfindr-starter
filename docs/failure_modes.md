# FitFindr — Deliberately Triggered Failure Modes

Evidence for Milestone 5. Each of the three tools' failure modes was triggered
on purpose from the terminal and confirmed to recover gracefully — returning a
specific, informative value rather than raising an exception. Automated coverage
for these same modes lives in `tests/test_tools.py`.

---

## 1. `search_listings` — zero results

**Command:**
```bash
python -c "from tools import search_listings; print(search_listings('designer ballgown', size='XXS', max_price=5))"
```

**Output:**
```
[]
```
Returns an empty list, no exception.

**Full agent on the same impossible query** (`run_agent("designer ballgown size XXS under $5", ...)`):
```
error: I couldn't find any "designer ballgown" under $5 in size XXS right now. Try raising your budget, removing the size filter, or using different keywords.
fit_card: None
```
The agent stops at the empty-search gate, never calls `suggest_outfit`/`create_fit_card`
(`fit_card` stays `None`), and tells the user *what* failed and *what to try next* —
naming the actual query terms, not a generic "no results found."

---

## 2. `suggest_outfit` — empty wardrobe

**Command:**
```bash
python -c "
from tools import search_listings, suggest_outfit
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe
results = search_listings('vintage graphic tee', size=None, max_price=50)
print(suggest_outfit(results[0], get_empty_wardrobe()))
"
```

**Output:**
```
This Y2K baby tee is perfect for creating a playful, nostalgic look, and it pairs
well with high-waisted jeans, flowy skirts, or distressed denim shorts. The pastel
colors in the butterfly print complement soft, earthy tones like beige, mint, and
lavender, while also popping against richer colors like black or dark blue. Overall,
this tee suits a cottagecore or vintage-inspired aesthetic, ideal for casual,
laid-back outings or everyday wear with a touch of whimsy.
```
Returns useful general styling advice (non-empty string), no exception — and does
not invent specific items the user doesn't own.

---

## 3. `create_fit_card` — empty outfit string

**Command:**
```bash
python -c "
from tools import search_listings, create_fit_card
results = search_listings('vintage graphic tee', size=None, max_price=50)
print(create_fit_card('', results[0]))
"
```

**Output:**
```
Can't write a fit card without an outfit suggestion — try styling the item first.
```
Returns a descriptive error-message string, no exception. The guard runs before any
LLM call, so this is deterministic.

---

## Summary

| Tool | Failure triggered | Result | Exception? |
|------|-------------------|--------|------------|
| `search_listings` | no matches (`designer ballgown`, XXS, $5) | `[]`; agent gives a specific, actionable retry message | No |
| `suggest_outfit` | empty wardrobe | general styling advice (non-empty) | No |
| `create_fit_card` | empty outfit string | descriptive error-message string | No |
