#!/usr/bin/env python3
"""Build decks.sqlite from deck_stats.json (output of simulate.js)."""
import json, sqlite3, os, sys

here = os.path.dirname(os.path.abspath(__file__))
src = os.path.join(here, 'deck_stats.json')
dst = os.path.join(here, 'decks.sqlite')

data = json.load(open(src))
fields, rows, rules = data['fields'], data['rows'], data['rules']
idx = {f: i for i, f in enumerate(fields)}

if os.path.exists(dst):
    os.remove(dst)
db = sqlite3.connect(dst)
db.executescript('''
CREATE TABLE decks (
  deck_id INTEGER PRIMARY KEY,
  cards TEXT NOT NULL,              -- 52 chars, T = ten
  optimal_final INTEGER,
  tier INTEGER,
  fun_raw INTEGER,
  fun_pct INTEGER,
  mean_std INTEGER,
  skill_noise REAL
);
CREATE TABLE deck_stats (           -- classic game-flow book play-through (S17, DAS, max 2 hands)
  deck_id INTEGER PRIMARY KEY REFERENCES decks(deck_id),
  rules TEXT NOT NULL,
  rounds INTEGER, hands_played INTEGER, cards_used INTEGER,
  player_bj INTEGER, dealer_bj INTEGER,
  splits INTEGER, doubles INTEGER, pairs_dealt INTEGER,
  player_wins INTEGER, dealer_wins INTEGER, pushes INTEGER,
  dealer_21_3plus INTEGER, player_21_3plus INTEGER,
  dealer_busts INTEGER, player_busts INTEGER,
  book_final INTEGER,               -- final bankroll: $3,000 start, flat $100 bets, BJ +500/-250
  sim_win_pct REAL, sim_win_std REAL,   -- weighted over 200 stochastic "reasonable player" runs
  sim_pw REAL, sim_dw REAL, sim_push REAL,
  sim_pbj REAL, sim_dbj REAL, sim_p21 REAL, sim_d21 REAL,
  sim_pbust REAL, sim_dbust REAL,
  sim_book INTEGER, sim_book_std INTEGER,
  sim_mix_book INTEGER, sim_mix_std INTEGER, sim_mix_bust REAL,  -- chips 200/350/500 random
  sim_500_book INTEGER, sim_500_std INTEGER, sim_500_bust REAL,  -- flat $500
  m_dd REAL, m_split REAL, m_splitdbl REAL, m_win3c REAL,        -- daily-mission event
  m_winsoft REAL, m_winudog REAL, m_windbust REAL, m_winboth REAL,  -- rates (mean/deck)
  m_matchwin REAL,                                               -- P(match won) %

  player_win_pct REAL,              -- player_wins / (player_wins + dealer_wins) (book line)
  pd_ratio REAL                     -- player_wins / dealer_wins (book line)
);
CREATE INDEX idx_decks_tier ON decks(tier);
CREATE INDEX idx_decks_score ON decks(optimal_final);
CREATE INDEX idx_stats_pbj ON deck_stats(player_bj);
CREATE INDEX idx_stats_ratio ON deck_stats(pd_ratio);
''')

deck_cols = ['deck_id','cards','optimal_final','tier','fun_raw','fun_pct','mean_std','skill_noise']
stat_cols = ['rounds','hands_played','cards_used','player_bj','dealer_bj','splits','doubles',
             'pairs_dealt','player_wins','dealer_wins','pushes','dealer_21_3plus',
             'player_21_3plus','dealer_busts','player_busts','book_final',
             'sim_win_pct','sim_win_std','sim_pw','sim_dw','sim_push','sim_pbj','sim_dbj',
             'sim_p21','sim_d21','sim_pbust','sim_dbust','sim_book','sim_book_std',
             'sim_mix_book','sim_mix_std','sim_mix_bust','sim_500_book','sim_500_std','sim_500_bust',
             'm_dd','m_split','m_splitdbl','m_win3c','m_winsoft','m_winudog','m_windbust',
             'm_winboth','m_matchwin']

db.executemany(
    f"INSERT INTO decks VALUES ({','.join('?'*8)})",
    ([r[idx[c]] for c in deck_cols] for r in rows))

def stat_row(r):
    pw, dw = r[idx['player_wins']], r[idx['dealer_wins']]
    dec = pw + dw
    return ([r[idx['deck_id']], rules] + [r[idx[c]] for c in stat_cols]
            + [round(pw/dec, 4) if dec else None, round(pw/dw, 4) if dw else None])

db.executemany(
    f"INSERT INTO deck_stats VALUES ({','.join('?'*48)})",
    (stat_row(r) for r in rows))
db.commit()

n = db.execute('SELECT COUNT(*) FROM decks').fetchone()[0]
agg = db.execute('''SELECT SUM(player_bj), SUM(dealer_bj), SUM(pushes),
  ROUND(1.0*SUM(player_wins)/SUM(dealer_wins),4), SUM(dealer_21_3plus) FROM deck_stats''').fetchone()
print(f'decks.sqlite built: {n} decks | player_bj={agg[0]} dealer_bj={agg[1]} '
      f'pushes={agg[2]} pd_ratio={agg[3]} dealer_21_3plus={agg[4]}')
db.close()
