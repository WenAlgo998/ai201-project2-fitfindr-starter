# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Searches the 40-item mock listings dataset (`data/listings.json`, loaded via `load_listings()`) for pieces matching the user's request. It applies an optional price ceiling and optional size filter, then scores the remaining listings by keyword overlap between the `description` and each listing's `title` + `description` + `style_tags`, dropping zero-score listings and returning the rest sorted best-match-first. Pure Python — no LLM call, so results are deterministic.

**Input parameters:**
- `description` (str): free-text keywords describing the desired item, e.g. `"vintage graphic tee"`. Lowercased and split into tokens that are matched against each listing's text fields for the relevance score.
- `size` (str | None): a size string to filter by, or `None` to skip size filtering. Matched case-insensitively as a substring so `"m"` matches `"S/M"`, `"M"`, and `"M/L"`. `None` is the common case because most queries omit size.
- `max_price` (float | None): inclusive maximum price in dollars, or `None` to skip price filtering. A listing passes when `listing["price"] <= max_price`.

**What it returns:**
A `list[dict]`, sorted by descending relevance score. Each element is a full listing dict with these keys: `id` (str), `title` (str), `description` (str), `category` (str), `style_tags` (list[str]), `size` (str), `condition` (str: excellent/good/fair), `price` (float), `colors` (list[str]), `brand` (str | None), `platform` (str: depop/thredUp/poshmark). Returns an empty list `[]` when nothing matches — it never raises.

**What happens if it fails or returns nothing:**
On no match it returns `[]` (it does not raise). The *planning loop* — not this tool — detects the empty list, writes a helpful error into the session, and stops before the downstream tools. See the Planning Loop and Error Handling sections.

---

### Tool 2: suggest_outfit

**What it does:**
Takes the thrifted item the user is considering and their existing wardrobe and asks the LLM (Groq) to suggest 1–2 complete outfits that pair the new item with specific pieces the user already owns. If the wardrobe is empty, it instead returns general styling advice for the item on its own so a brand-new user still gets a useful answer.

**Input parameters:**
- `new_item` (dict): a single listing dict — the item being styled (normally `search_results[0]`). Its `title`, `category`, `colors`, and `style_tags` are formatted into the prompt so the suggestion fits the actual piece.
- `wardrobe` (dict): a wardrobe dict shaped `{"items": [...]}`, where each item has `id`, `name`, `category`, `colors`, `style_tags`, and optional `notes`. May be empty (`{"items": []}`); this is a defined branch, not an error.

**What it returns:**
A non-empty `str` of styling text. When the wardrobe has items, it names specific owned pieces by their `name` (e.g. "pair with your baggy dark-wash jeans and chunky white sneakers") and explains the resulting vibe. When the wardrobe is empty, it returns general styling ideas (what categories/colors pair well, what aesthetic it suits) instead. Never returns an empty string.

**What happens if it fails or returns nothing:**
The empty-wardrobe case is handled internally (general advice) and is not treated as a failure. The only real failure is the Groq API call raising (network/auth/rate-limit); the planning loop wraps the call, records the error in the session, leaves downstream fields `None`, and stops before `create_fit_card`.

---

### Tool 3: create_fit_card

**What it does:**
Turns the outfit suggestion into a short, casual social-media caption — the kind you'd post under an OOTD photo. Calls the LLM (Groq) at a higher temperature so the wording feels fresh and varies between runs.

**Input parameters:**
- `outfit` (str): the styling text returned by `suggest_outfit` — describes the look to caption.
- `new_item` (dict): the listing dict for the thrifted item, used so the caption can name the item, its `price`, and its `platform` naturally (once each).

**What it returns:**
A `str` of 2–4 sentences usable as an Instagram/TikTok caption: casual and authentic (not a product description), mentioning the item name + price + platform once each, naming the outfit vibe in specific terms, and reading differently for different inputs.

**What happens if it fails or returns nothing:**
If `outfit` is empty or whitespace-only, it returns a descriptive error-message string rather than raising. In the normal flow the loop only reaches this tool with a valid `outfit`, so the guard is a safety net for direct/standalone calls and for any upstream LLM hiccup.

---

### Additional Tools (if any)

None for the core build — the three required tools cover the full find → style → share flow. A possible stretch addition is a price-comparison tool (`assess_price(new_item)` returning a "deal / fair / overpriced" verdict with reasoning drawn from comparable listings in the dataset), noted here but not part of the core design.

---

## Planning Loop

**How does your agent decide which tool to call next?**

The loop is a fixed find → style → share sequence with conditional gates that can terminate it early. It is not a free-form "LLM picks the tool" loop; the *order* is fixed, but *whether it continues* depends on each step's output. Written as explicit branches:

1. **Initialize** the session with `_new_session(query, wardrobe)`.
2. **Parse** `query` into `description`, `size`, `max_price` and store in `session["parsed"]`:
   - Regex-extract a price from patterns like `under $30` / `$30` / `30 dollars` → `max_price` (else `None`).
   - Regex-extract a size from patterns like `size M` / `size 8` → `size` (else `None`).
   - Use the remaining cleaned text as `description`.
3. **Call** `search_listings(description, size, max_price)` and store the list in `session["search_results"]`.
   - **Branch A — `if not search_results:`** set `session["error"]` to a specific, actionable message and **`return session`** immediately. Do **not** call `suggest_outfit` or `create_fit_card`.
   - **Else** continue.
4. **Select** the top result: `session["selected_item"] = search_results[0]`.
5. **Call** `suggest_outfit(selected_item, wardrobe)`, wrapped in try/except:
   - On success, store the string in `session["outfit_suggestion"]`. (An empty wardrobe is handled *inside* the tool — it still returns text, so no branch is needed here.)
   - **Branch B — on exception** (Groq API error): set `session["error"]`, leave later fields `None`, and **`return session`**.
6. **Call** `create_fit_card(outfit_suggestion, selected_item)`, wrapped in try/except:
   - On success, store the string in `session["fit_card"]`.
   - **Branch C — on exception or empty caption**: set `session["error"]` and **`return session`**.
7. **Return** `session`.

**What state it checks:** the truthiness of `search_results` (Branch A) and whether the LLM calls succeed (Branches B/C). **How it knows it's done:** it reaches step 7 with `fit_card` set and `error is None`; alternatively it terminates at any branch that sets `error`. The caller distinguishes the two by checking `session["error"]` first.

---

## State Management

**How does information from one tool get passed to the next?**

A single **session dict** (built by `_new_session()` in `agent.py`) is the one source of truth for an interaction. Tools themselves stay stateless — they take plain arguments and return plain values; the planning loop is what reads each tool's output from the session and feeds it as the input to the next. This is what lets the item from `search_listings` reach `suggest_outfit`, and the outfit reach `create_fit_card`, without the user re-entering anything.

What is stored, when it's written, and who reads it:

| Field | Written | Read by |
|-------|---------|---------|
| `query` | at init (user input) | parse step |
| `parsed` | after parse step | `search_listings` args |
| `search_results` | after `search_listings` | Branch A check, select step |
| `selected_item` | after select step (`search_results[0]`) | `suggest_outfit`, `create_fit_card` |
| `wardrobe` | at init (UI choice) | `suggest_outfit` |
| `outfit_suggestion` | after `suggest_outfit` | `create_fit_card` |
| `fit_card` | after `create_fit_card` | final output |
| `error` | at any early-exit branch | caller (checked first) |

**Data flow:** `query → parsed → search_results → selected_item → outfit_suggestion → fit_card`. The wardrobe is injected once at session creation (Example or Empty, per the UI radio) rather than parsed from the query. When the loop returns, the caller (`app.py`'s `handle_query`) reads the finished session: if `error` is set it shows that message; otherwise it formats `selected_item` and displays it alongside `outfit_suggestion` and `fit_card`.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | Tool returns `[]` (never raises). Loop hits Branch A, stops before the other tools, and tells the user *what* failed and *what to try*: e.g. "I couldn't find any vintage graphic tees under $10 — the closest are around $18. Try raising your budget to $20, removing the size filter, or using different keywords." (Message names the actual query terms and a concrete next step, not a generic error.) |
| suggest_outfit | Wardrobe is empty | Not a failure — a defined branch. The tool detects `wardrobe["items"] == []` and returns general styling advice for the item alone (what categories/colors/vibe pair well), so a new user with no closet still gets a styled answer instead of an error. |
| create_fit_card | Outfit input is missing or incomplete | Tool guards against an empty/whitespace `outfit` and returns a descriptive message string ("Can't write a fit card without an outfit suggestion — try styling the item first.") rather than raising. The loop normally only reaches it with a valid outfit, so this is a defensive safety net. |
| (any LLM tool) | Groq API call raises (network / auth / rate limit) | Loop wraps `suggest_outfit` / `create_fit_card` in try/except (Branches B/C), records a plain-language message in `session["error"]` ("Styling service is temporarily unavailable — please try again in a moment."), leaves downstream fields `None`, and returns so the UI surfaces it instead of crashing. |

---

## Architecture

```
User query + wardrobe choice
        │
        ▼
┌─────────────────────────────────────────────────────────────────────┐
│  app.py · handle_query()  — picks wardrobe, calls run_agent()         │
└───────────────────────────────┬───────────────────────────────────────┘
                                 │ query, wardrobe
                                 ▼
PLANNING LOOP  (agent.py · run_agent) ─────────────────────────────────┐
    │                                                                  │
    │  parse query ──────────────► SESSION.parsed                      │
    │       │ description, size, max_price                             │
    │       ▼                                                          │
    ├─► search_listings(description, size, max_price)                  │
    │       │                                                          │
    │       │ results == []                                            │
    │       ├──► SESSION.error = "No listings… try X" ──► return ───────┤
    │       │                                                          │
    │       │ results == [item, ...]                                   │
    │       ▼                                                          │
    │   SESSION.selected_item = results[0]                             │
    │       │ selected_item                                            │
    │       ▼                                                          │
    ├─► suggest_outfit(selected_item, wardrobe) ──[Groq LLM]           │
    │       │   (empty wardrobe → general advice, not an error)        │
    │       │ on API error ──► SESSION.error ──► return ────────────────┤
    │       ▼                                                          │
    │   SESSION.outfit_suggestion = "..."                              │
    │       │ outfit_suggestion, selected_item                         │
    │       ▼                                                          │
    └─► create_fit_card(outfit_suggestion, selected_item) ──[Groq LLM] │
            │   on error/empty ──► SESSION.error ──► return ───────────┤
            ▼                                                          │
        SESSION.fit_card = "..."                            error path │
            │                                               returns ───┘
            ▼
        return SESSION  ──────────────────────►  back to app.py UI
                                                 (3 panels OR error)

   ┌──────────────────────── SESSION STATE (dict) ────────────────────────┐
   │ query · parsed · search_results · selected_item · wardrobe ·          │
   │ outfit_suggestion · fit_card · error                                  │
   │ (every loop step reads/writes here — the only shared state)           │
   └───────────────────────────────────────────────────────────────────────┘

   DATA SOURCES:  search_listings ← load_listings() (data/listings.json, pure Python)
                  suggest_outfit, create_fit_card ← Groq LLM (GROQ_API_KEY)
```

**Reading the diagram:** a user query triggers the loop; a non-empty `search_results` triggers `suggest_outfit`; a valid `outfit_suggestion` triggers `create_fit_card`. The three `── return ──┤` arrows on the right are the error branch — any gate that sets `SESSION.error` jumps straight to `return SESSION`, skipping the remaining tools. All steps read and write the single session dict.

---

## AI Tool Plan

**Milestone 3 — Individual tool implementations:**

- **`search_listings` (pure Python).** *AI tool:* Claude. *Input I'll give it:* the **Tool 1** block above (signature, the three params, the substring size-matching rule, the keyword-overlap scoring + drop-zero + sort rules) plus the `load_listings()` docstring from `utils/data_loader.py`. *Expected output:* the function body only, keeping the existing signature, with no LLM call. *Verification:* before running, I'll read the code to confirm it filters by all three parameters and returns `[]` on no match. Then I'll test three queries: `("vintage graphic tee", None, 30.0)` should surface tees like `lst_033`/`lst_006`/`lst_002`; adding `size="M"` should narrow given the messy size strings; `("designer ballgown", "XXS", 5.0)` must return `[]`.
- **`suggest_outfit` + `create_fit_card` (LLM-backed).** *AI tool:* Claude. *Input I'll give it:* the **Tool 2** and **Tool 3** blocks (including the empty-wardrobe branch and the caption style rules) plus the `_get_groq_client()` helper. *Expected output:* prompt construction + a Groq call per tool, higher temperature for the fit card. *Verification:* call `suggest_outfit` once with `get_example_wardrobe()` (must name real owned pieces) and once with `get_empty_wardrobe()` (must still return non-empty general advice); call `create_fit_card` on the result and check it mentions item name + price + platform once each and reads casually; run it twice to confirm the output varies.

**Milestone 4 — Planning loop and state management:**

- **`run_agent` (the loop).** *AI tool:* Claude. *Input I'll give it:* the **Planning Loop** section (the numbered branches A/B/C), the **State Management** table, the **Error Handling** table, and the **Architecture** diagram above, plus the `run_agent`/`_new_session` docstrings. *Expected output:* `run_agent()` implementing the parse step, the `search_listings` call, the empty-result early return (Branch A), selection, and the two wrapped LLM calls — matching the session-dict contract. *Verification:* run `python agent.py`, which exercises both the happy path (expects found item + outfit + fit card, `error is None`) and the no-results path (expects `error` set, downstream fields `None`). I'll confirm the same `selected_item` object flows into both downstream tools (no re-search).
- **`handle_query` (the UI glue).** *AI tool:* Claude. *Input I'll give it:* the **State Management** section (how the caller reads the finished session) plus the `handle_query` docstring in `app.py`. *Expected output:* empty-query guard, wardrobe selection from the radio, `run_agent` call, and mapping of the session to the three panels (or the error message to panel 1). *Verification:* run `python app.py` and try the built-in example queries including the deliberate no-results one, confirming the error shows in panel 1 with the other two blank.
- **Guardrail across both:** before trusting any generated body I'll check it didn't change a tool signature and didn't bypass the session dict — those two contracts are what the rest of the code depends on.

---

## A Complete Interaction (Step by Step)

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.

**What FitFindr needs to do (in my own words):**
FitFindr is a thrift-shopping assistant that finds a real secondhand listing matching what the user wants, then styles it against the clothes they already own. A user request triggers `search_listings` (filtering the 40-item dataset by description/style, size, and max price); the top match then triggers `suggest_outfit`, which pairs that item with pieces from the user's wardrobe; that styling suggestion finally triggers `create_fit_card`, which writes a short, casual social-style caption for the look. On failure the agent stops gracefully rather than passing empty data forward: if `search_listings` returns nothing, FitFindr tells the user what to change (loosen the price, drop the size filter, try different terms) and does **not** call `suggest_outfit`; if the wardrobe is empty, `suggest_outfit` can only describe the item on its own; and `create_fit_card` is skipped if there's no valid outfit to caption.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1 — Search:** The agent calls `search_listings("vintage graphic tee", max_price=30.0)` (no size given, so the size filter is left off). Against `listings.json` this matches items tagged `graphic tee`/`vintage` under $30 — e.g. `lst_033` "Vintage Band Tee — Faded Grey" ($19), `lst_006` "Graphic Tee — 2003 Tour Bootleg Style" ($24), and `lst_002` "Y2K Baby Tee — Butterfly Print" ($18). Results come back sorted by relevance; the agent picks the top one, say `lst_033` "Vintage Band Tee — Faded Grey, $19, Depop, fair condition."

**Step 2 — Suggest outfit:** Passing the chosen listing as `new_item` and the user's wardrobe (`get_example_wardrobe()`) into `suggest_outfit(new_item=<band tee>, wardrobe=<wardrobe>)`. It finds matching pieces — the baggy dark-wash jeans (`w_001`) and chunky white sneakers (`w_007`) — and returns styling text like: "Wear this faded band tee with your baggy dark-wash jeans and chunky white sneakers for an easy 90s grunge look. Half-tuck the front to break up the boxy fit."

**Step 3 — Fit card:** The agent calls `create_fit_card(outfit=<suggestion>, new_item=<band tee>)`, which turns the look into a short caption: "thrifted this faded band tee off depop for $19 🖤 paired it with my baggy jeans + chunky sneakers, total 90s grunge energy."

**Final output to user:** The user sees the matched listing (title, price, platform, condition), the styling suggestion tying it to clothes they already own, and the ready-to-post fit card caption — a complete find-it / style-it / share-it answer.

**Error path example:** If the user asked for "a vintage graphic tee under $10," `search_listings` returns nothing. FitFindr stops there and replies: "No vintage graphic tees under $10 right now — the closest are around $18. Want me to raise the budget to $20?" It does **not** call `suggest_outfit` or `create_fit_card` with empty input.
