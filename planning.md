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
<!-- Describe what this tool does in 1–2 sentences -->

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `description` (str): ...
- `size` (str): ...
- `max_price` (float): ...

**What it returns:**
<!-- Describe the return value — what fields does a result contain? -->

**What happens if it fails or returns nothing:**
<!-- What should the agent do if no listings match? -->

---

### Tool 2: suggest_outfit

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `new_item` (dict): ...
- `wardrobe` (dict): ...

**What it returns:**
<!-- Describe the return value -->

**What happens if it fails or returns nothing:**
<!-- What should the agent do if the wardrobe is empty or no outfit can be suggested? -->

---

### Tool 3: create_fit_card

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `outfit` (...): ...

**What it returns:**
<!-- Describe the return value -->

**What happens if it fails or returns nothing:**
<!-- What should the agent do if the outfit data is incomplete? -->

---

### Additional Tools (if any)

<!-- Copy the block above for any tools beyond the required three -->

---

## Planning Loop

**How does your agent decide which tool to call next?**
<!-- Describe the logic your planning loop uses. What does it look at? What conditions change its behavior? How does it know when it's done? -->

---

## State Management

**How does information from one tool get passed to the next?**
<!-- Describe how your agent stores and accesses state within a session. What data is tracked? How is it passed between tool calls? -->

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | |
| suggest_outfit | Wardrobe is empty | |
| create_fit_card | Outfit input is missing or incomplete | |

---

## Architecture

<!-- Draw a diagram of your agent showing how the components connect:
     User input → Planning Loop → Tools (search_listings, suggest_outfit, create_fit_card)
                                                                          ↕
                                                                   State / Session
     Show what triggers each tool, how state flows between them, and where error paths branch off.
     ASCII art, a Mermaid diagram (https://mermaid.js.org/syntax/flowchart.html), or an embedded
     sketch are all fine. You'll share this diagram with an AI tool when asking it to implement
     the planning loop and each individual tool. -->

---

## AI Tool Plan

<!-- For each part of the implementation below, describe:
     - Which AI tool you plan to use (Claude, Copilot, ChatGPT, etc.)
     - What you'll give it as input (which sections of this planning.md, your agent diagram)
     - What you expect it to produce
     - How you'll verify the output matches your spec before moving on

     "I'll use AI to help me code" is not a plan.
     "I'll give Claude my Tool 1 spec (inputs, return value, failure mode) and ask it to implement
     search_listings() using load_listings() from the data loader — then test it against 3 queries
     before trusting it" is a plan. -->

**Milestone 3 — Individual tool implementations:**

**Milestone 4 — Planning loop and state management:**

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
