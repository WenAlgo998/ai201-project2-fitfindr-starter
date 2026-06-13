# FitFindr 🛍️

FitFindr is a secondhand-fashion shopping agent. You describe what you're
looking for in plain language; it finds a matching thrifted listing, styles it
against the clothes you already own, and writes a casual social-media caption
("fit card") for the look. It runs as a small Gradio web app backed by a
three-tool planning loop.

A full interaction is **find → style → share**:

> *"I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans
> and chunky sneakers."*
> 1. **search** the listings for a vintage graphic tee under $30 →
> 2. **style** the top match against your wardrobe →
> 3. **caption** the resulting outfit as a shareable fit card.

---

## Setup

```bash
pip install -r requirements.txt
```

Add your Groq API key to a `.env` file in the project root (free key at
[console.groq.com](https://console.groq.com)):

```
GROQ_API_KEY=your_key_here
```

## Run

```bash
python app.py
```

Open the URL printed in your terminal — usually **http://localhost:7860**, but
check the output, as the port can differ. Enter a query, pick a wardrobe
(Example or Empty), and hit **Find it**. All three panels — listing, outfit
idea, fit card — populate on a happy-path query.

You can also run the agent headless:

```bash
python agent.py        # runs a happy-path query and a no-results query
pytest tests/          # 11 tool tests (live-LLM tests skip without a key)
```

---

## Tool Inventory

All three tools live in `tools.py` and are callable in isolation.

### 1. `search_listings(description, size, max_price) -> list[dict]`

**Purpose:** find listings in the 40-item mock dataset that match the user's
request. Pure Python (no LLM) via `utils.data_loader.load_listings()`, so it's
deterministic.

| Parameter | Type | Meaning |
|-----------|------|---------|
| `description` | `str` | keywords describing the item, e.g. `"vintage graphic tee"`. Tokenized and matched for relevance. |
| `size` | `str \| None` | size filter; case-insensitive **substring** match (`"M"` matches `"S/M"`, `"M/L"`). `None` skips size filtering. |
| `max_price` | `float \| None` | inclusive price ceiling. `None` skips price filtering. |

**Returns:** a `list[dict]` of listings sorted by descending relevance. Each
dict has `id`, `title`, `description`, `category`, `style_tags` (list), `size`,
`condition`, `price` (float), `colors` (list), `brand` (str or `None`),
`platform`. Returns `[]` when nothing matches — never raises.

**How relevance works:** the description is lowercased and split into tokens
(short words and a small stopword set are dropped); each surviving token that
appears in a listing's title + description + style_tags scores +1. Zero-score
listings are dropped; the rest are sorted highest-first.

### 2. `suggest_outfit(new_item, wardrobe) -> str`

**Purpose:** style the chosen item against the user's wardrobe. Calls the Groq
LLM (`llama-3.3-70b-versatile`).

| Parameter | Type | Meaning |
|-----------|------|---------|
| `new_item` | `dict` | a listing dict (normally `search_results[0]`) — the piece being styled. |
| `wardrobe` | `dict` | `{"items": [...]}`, each item with `id`, `name`, `category`, `colors`, `style_tags`, optional `notes`. May be empty. |

**Returns:** a non-empty `str`. With a populated wardrobe it names specific owned
pieces ("pair with your baggy straight-leg jeans and chunky white sneakers"); with
an empty wardrobe it returns general styling advice instead.

### 3. `create_fit_card(outfit, new_item) -> str`

**Purpose:** turn the outfit into a short, casual OOTD-style caption. Calls the
Groq LLM at a higher temperature (1.1) so repeated captions vary.

| Parameter | Type | Meaning |
|-----------|------|---------|
| `outfit` | `str` | the styling text from `suggest_outfit`. |
| `new_item` | `dict` | the listing dict, so the caption can name the item, price, and platform. |

**Returns:** a 2–4 sentence `str` caption mentioning the item name, price, and
platform once each. If `outfit` is empty/whitespace it returns a descriptive
error-message string instead of raising.

---

## Planning Loop

The loop (`run_agent()` in `agent.py`) is a **fixed find → style → share
sequence with conditional gates that can end it early**. The order of tools is
fixed; what changes per query is *whether the loop continues or stops*, based on
each step's output. It does **not** call all three tools unconditionally.

1. **Initialize** the session (`_new_session`).
2. **Parse** the query into `description`, `size`, `max_price` (regex — see
   State Management). Store in `session["parsed"]`.
3. **Search:** call `search_listings(**parsed)`.
   - **Decision (Branch A):** `if not search_results:` → write a specific,
     actionable message to `session["error"]` and **return early**.
     `suggest_outfit` and `create_fit_card` are never called.
   - else → continue.
4. **Select** `session["selected_item"] = search_results[0]`.
5. **Suggest outfit** (wrapped in try/except). An empty wardrobe is *not* an
   error — the tool returns general advice — so the loop proceeds. On an LLM
   exception (**Branch B**) it sets `error` and returns.
6. **Create fit card** (wrapped in try/except). On exception/empty (**Branch
   C**) it sets `error` and returns.
7. **Return** the session.

**What state it checks:** the truthiness of `search_results` (Branch A) and
whether the LLM calls succeed (Branches B/C). **How it knows it's done:** it
reaches step 7 with `fit_card` set and `error is None`; otherwise it terminates
at whichever gate set `error`. The caller checks `session["error"]` first to
tell success from early exit.

---

## State Management

A single **session dict** (built by `_new_session()`) is the one source of
truth for an interaction. Tools are stateless — they take plain arguments and
return plain values; the loop reads each tool's output from the session and
feeds it as the input to the next. This is what lets the item from
`search_listings` reach `suggest_outfit`, and the outfit reach
`create_fit_card`, **without the user re-entering anything**.

| Field | Written | Read by |
|-------|---------|---------|
| `query` | at init | parse step |
| `parsed` | after parse | `search_listings` args |
| `search_results` | after search | Branch A, select step |
| `selected_item` | after select (`search_results[0]`) | `suggest_outfit`, `create_fit_card` |
| `wardrobe` | at init (UI choice) | `suggest_outfit` |
| `outfit_suggestion` | after `suggest_outfit` | `create_fit_card` |
| `fit_card` | after `create_fit_card` | final output |
| `error` | at any early-exit branch | caller (checked first) |

**Data flow:** `query → parsed → search_results → selected_item →
outfit_suggestion → fit_card`. Verified by object identity:
`selected_item is search_results[0]` and `selected_item` is the exact dict
passed into `suggest_outfit`; `outfit_suggestion` is the exact string passed
into `create_fit_card`. The wardrobe is injected once at session creation from
the UI radio, not parsed from the query.

**Query parsing** is regex-based (not LLM): a price is pulled from patterns like
`under $30` / `$30` / `30 dollars`; a size from the explicit `size X` form; the
remaining cleaned text becomes the description.

---

## Error Handling

| Tool | Failure mode | What the agent does |
|------|-------------|---------------------|
| `search_listings` | no results match | returns `[]` (no exception); the loop hits Branch A, stops before the other tools, and returns a message naming the query terms and concrete next steps |
| `suggest_outfit` | empty wardrobe | not an error — returns general styling advice so a new user still gets a styled answer |
| `create_fit_card` | empty/whitespace outfit | returns a descriptive message string ("Can't write a fit card without an outfit suggestion…") rather than raising |
| `suggest_outfit` / `create_fit_card` | Groq API raises | loop's try/except records a plain-language message in `session["error"]`, leaves later fields `None`, and returns |

**Concrete example from testing** (the impossible query
`"designer ballgown size XXS under $5"`):

```
$ python -c "from tools import search_listings; print(search_listings('designer ballgown', size='XXS', max_price=5))"
[]

# full agent on the same query:
error: I couldn't find any "designer ballgown" under $5 in size XXS right now.
       Try raising your budget, removing the size filter, or using different keywords.
fit_card: None
```

The agent stops at the empty-search gate, never calls the downstream tools
(`fit_card` stays `None`), and tells the user *what* failed and *what to try*.
All three triggered failures are recorded in
[`docs/failure_modes.md`](docs/failure_modes.md); automated coverage is in
`tests/test_tools.py`.

---

## Spec Reflection

**One way the spec helped:** writing the State Management section of
`planning.md` *first* — as a per-field table of what's stored and who reads it —
made wiring `run_agent()` almost mechanical. Because the session-dict contract
was pinned down before any loop code existed, the tools stayed fully decoupled
(plain args in, plain values out) and threading state between them was just
"write field, read field." It also gave a precise thing to test: I could assert
by object identity that the *same* listing dict flows from search into
`suggest_outfit`, which is exactly the no-re-entry property the loop needed.

**One divergence and why:** the planning.md walkthrough predicted
`"vintage graphic tee"` would surface a band tee (`lst_033`) as the top result.
In practice the top result is the Y2K Baby Tee (`lst_002`), because `"vintage"`
is such a common tag that simple keyword-overlap scoring ranks several tees
similarly and ties break by dataset order. A sharper case: `"black combat boots
size 8"` returns *Suede Chelsea Boots* — the dataset has no black combat boots,
so the agent surfaces the closest keyword + size match rather than nothing.
I kept this behavior (surfacing the nearest match) rather than tightening the
scoring, because for a shopping assistant a near match is more useful than an
empty result — but it's a real gap between the planned example and actual
output, and a fuzzier/weighted scorer would be the next improvement.

---

## AI Usage

I used **Claude (via Claude Code)** as my implementation assistant, driving it
one spec block at a time from `planning.md`.

**Instance 1 — `search_listings`.** I gave Claude the Tool 1 spec block (the
signature, the substring size rule, and the "score by keyword overlap → drop
zero → sort" steps) plus the `load_listings()` docstring, and asked it to
implement just that function. The first version did plain token-overlap
scoring. I **revised it** to drop a small set of stopwords (`the`, `with`,
`under`, `size`, …) and any token under 3 characters, because otherwise common
connective words in a description inflated relevance scores and flattened the
ranking. I verified the change against three queries (a normal search, the
empty `designer ballgown` case, and a price-filter check) before trusting it.

**Instance 2 — the planning loop (`run_agent`).** I gave Claude the Planning
Loop section, the State Management table, and the architecture diagram, and
asked it to implement the loop. I reviewed the result specifically against my
spec's branch logic: it correctly returned early on empty search results, but I
**verified by instrumentation** (wrapping the tools to record what objects they
received) that `selected_item` was the *same* dict passed into `suggest_outfit`
and that `suggest_outfit` was *not* called on the no-results path — the
"behaves differently per input" requirement. I also **overrode the parsing
approach**: rather than have the LLM parse the query, I kept it regex-based so
the search step stays deterministic and testable.

**Instance 3 — fit-card variety.** When wiring `create_fit_card`, repeated calls
on the same input read too similarly. I **raised the temperature to 1.1** and
added a test (`test_fit_card_varies_on_repeat`) asserting two calls differ,
rather than assuming the default temperature gave enough variation.
