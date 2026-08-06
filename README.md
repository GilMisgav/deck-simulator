# Deck Room — Blackjack Deck Simulator & Database

Simulator, analytics dashboard, and database for the 27,355 decks in
`decks_filtered (1).json`, built around an **exact mirror of the SwiftGames
classic Blackjack flow** (`SwiftClient/CasualGames/Games/Blackjack/BlackjackViewModel.swift`).

## Rules (classic game flow)

Deal order **P1 · P2 · dealer-up · hole** (PT-69 §4.2) · naturals settled **flat before
betting** (player BJ **+$500**, dealer BJ **−$250**, both = push, no stake taken) · bet after
deal, blind on the up-cards (chips **100/200/500/1000**, lowest floors to bankroll) ·
bankroll **$3,000** · dealer **stands on all 17s (S17)** · split **max 2 hands, by value**,
DAS, split aces one card · auto-stand on 21 · dealer skips drawing when every hand busted ·
deck never reshuffled — the hand that starts at **≤12 cards is the LAST** ·
"21 (3+)" = a total of exactly 21 made with three or more cards ("opened 21").
The book baseline (database stats + auto-play) bets flat $100; `book_final` is its
end-of-deck bankroll. Sanity check: the filtered decks contain **zero first-round
naturals** under this deal order — the upstream filter removed them, confirming the order.

## Files

| File | What it is |
|---|---|
| `index.html` + `data.js` | The app — open in a browser (Analytics / Database / Strategy / Generate / Play) |
| `server.js` | Zero-dependency Node server: static files + **save-to-database API** |
| `start.command` | Double-click launcher — starts `server.js` and opens the app |
| `decks.sqlite` | SQLite database: `decks` (original 8 fields) + `deck_stats` (simulated stats) |
| `removed_decks.json` | Archive of permanently deleted decks (created on first delete; restorable) |
| `simulate.js` | Batch profiler — `node simulate.js <input.json>` → `data.js`, `deck_stats.json` |
| `build_sqlite.py` | Rebuilds `decks.sqlite` from `deck_stats.json` |

## Online copy

Live at **https://gilmisgav.github.io/deck-room/** (GitHub Pages, repo
`GilMisgav/deck-room`, anyone with the link). Everything works in the browser
except permanent delete / add-to-database (those need the local server).
After local changes — deletions, added generated decks, UI updates — double-click
`publish.command` to push the refreshed app + database online (~1 min to go live).

## Run

Double-click `start.command`, or:

```bash
node /Users/gilmisgav/Economy/deck-simulator/server.js
# → http://localhost:8642/  (with the save-to-database API)
```

(Also registered as the `deck-simulator` preview config in `.claude/launch.json`.
A plain `python3 -m http.server` or opening `index.html` directly still works, but
is view-only — deletions can't be saved without `server.js`.)

## Journey (FIFO deck sequences)

The **Journey** tab builds the ordered list of decks a player will experience,
first-in-first-out. Add decks by id, +5 random from the current filter, or tick
rows in the Database and press *Add to journey*. Controls: per-row reorder/remove,
**pacing presets** (Ease-in kind→tough, Tough start, Roller-coaster, Shuffle — all
ordered by weighted sim win %), and an expected-net **bet model** selector
(flat $100 / chips 200/350/500 / flat $500). Graphs: the **experience curve**
(expected win % per position ±1σ with actual results overlaid as dots) and
**cumulative net** (expected running net ±1σ vs actual). *Play journey* opens the
next unplayed deck; finishing a deck (manually or auto-play) records its actual
result and queues the next one (button or Enter). Summary tiles show expected vs
actual totals, toughest deck, and bust risk. The journey persists in the browser
(localStorage) across reloads.

**Bulk add with requirements** — pick a count and minimum/maximum KPIs
(P BJ ≥, Splits ≥, Doubles ≥, P21+ ≥, Pushes ≥, sWin% ≥, D BJ ≤, Bust% ≤) and the
builder appends N random matching decks from the current Database filter,
skipping decks already in the journey and reporting the size of the matching pool.

**Missions per stage** — for every journey stage, a matrix counts how many times
each mission from `Blackjack_Missions_One_Deck.xlsx` happens on the deterministic
active-sheet line: Opening (Any Pair, Blackjack, Pocket Aces, Hard 20, Starting 11),
21+3 (Pair, Trips, Straight), 4 Cards (Two Pair, Trips, Straight, Quads),
Gameplay (Reach 21, Win 5+/6+ cards, Win after Double, Win Split Hand) and
Dealer Busts (any / 5+ / 6+ cards) — 20 rank-based missions of the sheet's 30;
the 10 suit-based ones (flushes, same suit/color, suited BJ, mixed/colored/perfect
pairs) aren't evaluable because decks store ranks only. A "Missions covered x/20"
tile and per-stage totals row summarize coverage; engine validated against the
stored book stats (Blackjack ≡ player_bj, Dealer Bust ≡ dealer_busts).
The matrix has a **sum range** (e.g. Σ stages 1–4; out-of-range stages dim) and a
**runs/deck** control (default 100, max 500): with runs > 1 every cell is the
weighted mean over seeded reasonable-player runs — the same seeds and deviation
model as the sim_* columns, so at 200 runs the mission averages reproduce them
exactly. runs = 1 shows the single deterministic active-sheet line. Averages are
cached per deck and invalidated when the strategy sheet or H17 changes.

**Sharing** — journeys live in each visitor's own browser (localStorage), so a
plain link never carries them. **Share link** encodes the whole journey (deck ids,
order, bet model, mission range/runs — not personal results) into the URL hash;
anyone opening it gets the journey loaded (with a confirm if it would replace
theirs, and a warning for decks missing from their database). Share links built
on localhost automatically point at the online copy.

## Missions machine

The bank merges **Mission 3.0 (PRD, `Mission_3_0_Blackjack.pdf`)** and the daily-missions
spec — 13 types, each tagged by source (M3 / D / both) and auto-assigned a **difficulty
tier** from the pool's simulated rate (PRD §6.1: ≥0.45/deck easy · ≥0.12 medium · below
hard). New M3 types: *Make 21s (non-BJ)* (`sim_p21`) and *Fast Scorer* — P(reach $5,000
within the first X hands), simulated live under chip-mix betting on demand. The
**experience composer** picks a chain for you: mission count, **effort** (Easy 50% →
Grind 130% of expected events), **comfort-zone ratio** (share of easy-tier vs stretch
missions, PRD's 70/30), and **experience arc** (quick wins first / hard opener / mixed) —
then sets targets, builds the delivering journey, and reports coverage. Exports:
daily-spec scripted config, or a **Mission 3.0 cycle config** (mission pool with
descriptions/tiers/tokens + Bonus-Cash chest milestones at 33/66/100% of total tokens).

The original inventory below is an inventory of the 11 daily-mission types from
`daily_missions_economy_spec_v2.md` (blackjacks, doubleDowns, splits, splitThenDouble,
winWith3PlusCards, winSoftHand, winUnderdogStart, winDealerBustLowHand,
winBothSplitHands, winPVP, winPvpStreak), each measured **per deck** by the weighted
200-run reasonable-player sim (m_* columns; winPVP = P(final > $3,000); streak
probability is an exact DP over the journey's per-deck odds). Working definitions:
underdog start = hard 12–16 vs dealer 9/10/A; dealer-bust low hand = win standing ≤16
on a dealer bust. Tick missions → *Suggest targets* (~75% of expected events for the
chosen deck count) → *Build journey for missions* greedily assembles the deck sequence
whose expected events cover every target (loads it as the Journey, with a delivery
report: expected vs target, covered-by stage, streak chance) → *Export missions
config* downloads a scripted config in the spec's exact format (rewards are
placeholders per its §6). Note: this is the daily-missions spec format — the backoffice
"Side Bets – Missions" bundle format (mission-bundle-manager skill) needs its Notion
page and stays blocked until Notion/Chrome is connected.

## Weighted "reasonable player" simulation (sim_* columns)

The single book line is fragile — one different close call reroutes every card after
it. So every deck also carries **weighted KPIs: the mean over 200 seeded stochastic
runs** where a "reasonable player" diverges from the book on close calls:

| Close call | Alternative | Share taking it |
|---|---|---|
| hard 16 vs 9/10/A | stand instead of hit | 45% |
| hard 15 vs 10/A | stand instead of hit | 35% |
| hard 12 vs 2/3 | stand instead of hit | 30% |
| hard 12 vs 4–6 | hit instead of stand | 25% |
| soft 18 vs 9/10/A | stand instead of hit | 50% |
| any double | just hit | 30% (10/11) · 45% (9) · 55% (soft) |
| split (non-aces) | play as a plain total | 35% (40% for 8,8 vs 9/10/A) |

A,A always splits; 10,10 always stands. Columns: `sim_win_pct ± sim_win_std`,
`sim_pw/sim_dw/sim_push`, `sim_pbj/sim_dbj`, `sim_p21/sim_d21`, `sim_pbust/sim_dbust`,
`sim_book ± sim_book_std`. Each run is also played under two extra **bet models**:
chip mix (a random affordable chip from 200/350/500 each hand, lowest floors to
bankroll) → `sim_mix_book ± sim_mix_std` + `sim_mix_bust` (% of runs bankrupt), and
flat $500 → `sim_500_book ± sim_500_std` + `sim_500_bust`. The same decision seed is
used across the three models, so bet size is the only initial difference. The Play
view shows the per-deck bankroll outlook line. They appear in the Database table (sWin %, sBook $…),
Analytics cards/histogram/tier table, the Play deck bar, filters, smart filter
("sim win over 55"), and exports. Runs are seeded per (deck, run) — fully reproducible.
Refresh after strategy changes or deletions: `node simulate.js && python3 build_sqlite.py`
(reads the current `deck_stats.json`, so deleted decks stay deleted).

## Persistent deletion

**Remove selected (n)** permanently deletes the checked decks from `data.js`,
`deck_stats.json` and `decks.sqlite` (one confirmation dialog) — the database
reflects your desired deck list across sessions, reloads and exports. Deleted
decks are archived to `removed_decks.json`; **Restore archived (n)** merges them
all back and rebuilds. To trim by rule: smart-filter (e.g. `delete decks with
dealer bj more than 1`) → Select all (n) → Remove selected. Without `server.js`
running, Remove selected falls back to session-only removal and says so.

## Rebuild from a new decks JSON

```bash
node simulate.js /path/to/decks.json   # simulate all decks, write data.js + deck_stats.json
python3 build_sqlite.py                # rebuild decks.sqlite
```

## App features

- **Analytics** — totals & per-deck averages for player/dealer blackjacks, pushes,
  player-vs-dealer win ratio and win %, 21s opened (player & dealer, 3+ cards),
  splits, doubles, busts; per-deck distributions; tier breakdown. Respects active filters.
- **Database** — filter on any metric (tier, score, fun %, skill noise, BJs, pushes,
  win %, 21s, splits, doubles, book $, deck-id search), every column sortable, paginated,
  with per-deck checkboxes (page select-all / select filtered) for hand-picking, and
  **Remove selected** to exclude checked decks from the view/export (a chip restores them).
  Every column header has a tooltip explaining the metric.
  A **smart filter** accepts plain-English commands — `remove decks where dealer makes
  21 more than 2 times`, `no dealer blackjacks`, `dealer busts at least twice`,
  `player hit 21 twice or more`, `book final between 2800 and 3500`, `sort by dealer bj`,
  `clear` — verbs (make/hit/reach/open), word numbers (twice, three), and loose phrasing
  all parse into removable filter chips that compose with the range filters. **Export filtered** or **Export selected** writes JSON
  in the *same structure as the source file* (`deck_id, cards, optimal_final, tier,
  fun_raw, fun_pct, mean_std, skill_noise`); tick *include stats* to nest the stats.
- **Strategy** — loadable cheat sheets: *Book basic* (default), *DUEL chart* (with R/H
  surrender cells), and *Custom* — click any cell to cycle its action (editing a preset
  forks it into Custom). A **dealer hits soft 17 (H17)** toggle sits beside the sheet.
  *Apply & re-simulate* replays all 27,355 decks in the browser (~4s) and updates
  Analytics, the Database table, play baselines and the generator. Codes fall back
  when the action is unavailable (3+ cards): D/H→Hit, D/S→Stand, P/H→Hit, R/H→Hit
  (no surrender in this game) — so e.g. a 3-card 16 vs 10 hints *Hit*. The .sqlite file
  keeps the shipped Book·S17 baseline.
- **Generate** — clone the KPIs of a reference deck: check which stats must match
  (BJs, pushes, wins, 21s, splits…), set ± tolerances (or type explicit targets), and
  the generator shuffles fresh 52-card decks (~30k/s), keeping only those whose book
  play-through lands inside every tolerance. Results are playable and exportable;
  upstream fields are inherited from the reference and `generated_from` marks the source.
  Generated decks live only in the session — press **Add to database (n)** to save them
  permanently (playable after reload, filterable, exportable; weighted sim columns fill
  on the next `node simulate.js` run).
- **Play a Deck** — the full game round flow: deal (your second card face down, dealer
  shows one card) → bet with chips → reveal → hit/stand/double/split with book hints →
  dealer flips and draws with the game's cadence → result → next hand. Bankroll/bet/net
  strip, LAST HAND warning, naturals flash their flat bonus/penalty, keyboard shortcuts
  (Enter, 1-4 to bet, H/S/D/P/A), auto-play the rest by book, and an end-of-match report
  comparing your session (including final bankroll) to the book baseline in the database.
  Interactive engine and auto-play are verified byte-identical to the batch profiler
  (400 + 200 random decks, 0 mismatches incl. `book_final`).

## SQLite examples

```sql
-- decks where the player out-blackjacks the dealer and pushes are rare
SELECT d.deck_id, s.player_bj, s.dealer_bj, s.pushes, s.player_win_pct
FROM decks d JOIN deck_stats s USING(deck_id)
WHERE s.player_bj >= 2 AND s.dealer_bj = 0 AND s.pushes <= 1
ORDER BY s.player_win_pct DESC LIMIT 20;

-- average win ratio by tier
SELECT d.tier, ROUND(AVG(s.pd_ratio),3), ROUND(AVG(s.player_bj),2), ROUND(AVG(s.pushes),2)
FROM decks d JOIN deck_stats s USING(deck_id) GROUP BY d.tier ORDER BY d.tier;
```

Note: `optimal_final` / `tier` / `fun_*` / `mean_std` / `skill_noise` are carried over
verbatim from the source JSON (they come from the upstream scoring pipeline, which uses a
different betting config than the older `deck-database/engine.js` — its scores are not
reproducible with that engine).
