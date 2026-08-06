// ════════════════════════════════════════════════════════════════════
// Deck Simulator — batch profiler
// Exact mirror of the SwiftGames classic Blackjack flow
// (SwiftClient/CasualGames/Games/Blackjack/BlackjackViewModel.swift):
//   • deal order P1 → P2 → dealer-up → hole (PT-69 §4.2)
//   • naturals settled flat BEFORE betting: player BJ +500, dealer BJ −250
//   • bet after deal (book baseline bets flat $100, bankroll $3,000)
//   • split: max 2 hands, equal VALUE, split aces one card each (auto-stand)
//   • double: 2 cards, not split-ace, DAS allowed
//   • dealer stands on all 17s (S17); skips drawing when every hand busted
//   • server deck never reshuffled; the hand that starts at ≤12 cards is the LAST
// Decisions use the basic-strategy book (same table as the in-game hint).
// Usage: node simulate.js <input.json>
// Writes: data.js (window.DECK_DATA) + deck_stats.json
// ════════════════════════════════════════════════════════════════════
'use strict';
const fs = require('fs');
const path = require('path');

const RANKVAL = {A:11,'2':2,'3':3,'4':4,'5':5,'6':6,'7':7,'8':8,'9':9,T:10,J:10,Q:10,K:10};

function total(cards){
  let t = 0, a = 0;
  for (const c of cards){ t += RANKVAL[c]; if (c === 'A') a++; }
  while (t > 21 && a > 0){ t -= 10; a--; }
  return [t, a > 0 && t <= 21];
}

// basic-strategy book (identical to the game's hint table)
function strategy(p, up, cd, cs, das = true){
  const n = p.length, [t, soft] = total(p);
  if (cs && n === 2 && RANKVAL[p[0]] === RANKVAL[p[1]]){
    const r = RANKVAL[p[0]], pr = p[0];
    if (pr === 'A') return 'P'; if (r === 10) return 'S';
    if (r === 9) return [2,3,4,5,6,8,9].includes(up) ? 'P' : 'S';
    if (r === 8) return 'P'; if (r === 7) return up <= 7 ? 'P' : 'H';
    if (r === 6) return (up <= 6 && (das || up >= 3)) ? 'P' : 'H';
    if (r === 5) return (up <= 9 && cd) ? 'D' : 'H';
    if (r === 4) return (das && (up === 5 || up === 6)) ? 'P' : 'H';
    if (r === 2 || r === 3) return up <= 7 ? 'P' : 'H';
  }
  if (soft){
    if (t >= 19) return 'S';
    if (t === 18){ if ([3,4,5,6].includes(up)) return cd ? 'D' : 'S'; if ([2,7,8].includes(up)) return 'S'; return 'H'; }
    if (t === 17) return ([3,4,5,6].includes(up) && cd) ? 'D' : 'H';
    if (t === 15 || t === 16) return ([4,5,6].includes(up) && cd) ? 'D' : 'H';
    if (t === 13 || t === 14) return ([5,6].includes(up) && cd) ? 'D' : 'H';
    return 'H';
  }
  if (t >= 17) return 'S'; if (t >= 13) return up <= 6 ? 'S' : 'H';
  if (t === 12) return [4,5,6].includes(up) ? 'S' : 'H';
  if (t === 11) return cd ? 'D' : 'H'; if (t === 10) return (up <= 9 && cd) ? 'D' : 'H';
  if (t === 9) return ([3,4,5,6].includes(up) && cd) ? 'D' : 'H'; return 'H';
}

const BET = 100, BJ_BONUS = 500, BJ_PENALTY = 250, LAST_AT = 12, START_BANKROLL = 3000;
const bookDecide = (cards, up, canD, canS) => strategy(cards, up, canD, canS, true);

// Game-flow rounds from an arbitrary position/bankroll — mutates and returns `s`.
// This exact function is mirrored in index.html (gameRoundsFrom); keep in sync.
function gameRoundsFrom(seq, startPos, startBankroll, s, decide, betFn, log){
  decide = decide || bookDecide;
  let pos = startPos, bankroll = startBankroll;
  while (true){
    if (bankroll <= 0) break;                    // BANKRUPT
    if (seq.length - pos < 4) break;             // cannot deal
    const last = (seq.length - pos) <= LAST_AT;  // LAST HAND rule
    s.rounds++;
    const p = [seq[pos++], seq[pos++]]; const d = [seq[pos++], seq[pos++]];
    const deal = log ? [p[0], p[1], d[0], d[1]] : null;
    const up = RANKVAL[d[0]];
    const pbj = total(p)[0] === 21, dbj = total(d)[0] === 21;
    if (pbj || dbj){                             // naturals settle flat, pre-bet
      s.hands_played++;
      if (pbj) s.player_bj++; if (dbj) s.dealer_bj++;
      let res;
      if (pbj && dbj){ s.pushes++; res = 'push — both blackjack'; }
      else if (pbj){ s.player_wins++; bankroll += BJ_BONUS; res = 'WIN — blackjack'; }
      else { s.dealer_wins++; bankroll = Math.max(0, bankroll - BJ_PENALTY); res = 'lose — dealer blackjack'; }
      if (log) log.push({deal, hands: [{cards: p.slice(), acts: [], res}], dealer: d.slice(), last});
      if (last) break;
      continue;
    }
    if (RANKVAL[p[0]] === RANKVAL[p[1]]) s.pairs_dealt++;
    const bet = betFn ? betFn(bankroll) : Math.min(BET, bankroll);  // lowest chip floors to bankroll
    bankroll -= bet;
    const hands = [{cards: p, bet, doubled: false, splitAce: false, acts: []}];
    for (let i = 0; i < hands.length; i++){
      const h = hands[i];
      while (true){
        if (h.splitAce) break;                   // split aces: one card, stood
        const t = total(h.cards)[0];
        if (t >= 21) break;                      // bust or auto-stand on 21
        const canS = hands.length < 2 && h.cards.length === 2 &&
          RANKVAL[h.cards[0]] === RANKVAL[h.cards[1]] &&
          bankroll >= h.bet && seq.length - pos >= 2;
        const canD = h.cards.length === 2 && !h.doubled &&
          bankroll >= h.bet && pos < seq.length;
        const a = decide(h.cards, up, canD, canS);
        if (a === 'P' && canS){
          s.splits++; bankroll -= h.bet;
          const isAces = h.cards[0] === 'A';
          const cSplit = h.cards.pop();
          const nh = {cards: [cSplit], bet: h.bet, doubled: false, splitAce: isAces, acts: []};
          h.cards.push(seq[pos++]); nh.cards.push(seq[pos++]);   // c1 then c2, like the game
          h.acts.push('split');
          hands.push(nh);
          if (isAces){ h.splitAce = true; break; }
          continue;
        }
        if (a === 'D' && canD){
          s.doubles++; bankroll -= h.bet; h.bet *= 2; h.doubled = true;
          const c = seq[pos++]; h.cards.push(c); h.acts.push('double→' + c); break;
        }
        if (a === 'H'){
          if (pos >= seq.length) break;
          h.cards.push(seq[pos++]); continue;
        }
        break;                                    // stand
      }
    }
    const allBust = hands.every(h => total(h.cards)[0] > 21);
    if (!allBust) while (total(d)[0] < 17 && pos < seq.length) d.push(seq[pos++]);
    const dt = total(d)[0]; const dbust = dt > 21;
    if (dbust) s.dealer_busts++;
    else if (dt === 21 && d.length >= 3) s.dealer_21_3plus++;
    for (const h of hands){
      s.hands_played++;
      const t = total(h.cards)[0];
      if (t > 21){ s.player_busts++; s.dealer_wins++; h.res = 'BUST — lose'; continue; }
      if (t === 21 && h.cards.length >= 3) s.player_21_3plus++;
      if (dbust || t > dt){ s.player_wins++; bankroll += h.bet * 2; h.res = 'WIN'; }
      else if (t < dt){ s.dealer_wins++; h.res = 'lose'; }
      else { s.pushes++; bankroll += h.bet; h.res = 'push'; }
    }
    if (log) log.push({deal, hands: hands.map(h => ({cards: h.cards.slice(), acts: h.acts, res: h.res})),
      dealer: d.slice(), last});
    if (last) break;
  }
  s.cards_used = pos;
  s.book_final = bankroll;
  return s;
}

function freshStats(){
  return {rounds:0, player_bj:0, dealer_bj:0, splits:0, doubles:0, pairs_dealt:0,
    player_wins:0, dealer_wins:0, pushes:0, dealer_21_3plus:0, player_21_3plus:0,
    dealer_busts:0, player_busts:0, hands_played:0, cards_used:0, book_final:0};
}
function playDeck(cardsStr){
  return gameRoundsFrom(cardsStr.split(''), 0, START_BANKROLL, freshStats());
}

// ── "reasonable player" stochastic model ────────────────────────────
// The book line is fragile: on close calls real players legitimately go either
// way, and one different decision reroutes every card after it. Each run draws
// a decision at every close call with these weights (share of reasonable
// players taking the alternative to the book action):
//   hard 16 vs 9/10/A : stand instead of hit  45%
//   hard 15 vs 10/A   : stand instead of hit  35%
//   hard 12 vs 2/3    : stand instead of hit  30%
//   hard 12 vs 4-6    : hit instead of stand  25%
//   soft 18 vs 9/10/A : stand instead of hit  50%
//   any double        : just hit instead      30% (11) / 30% (10) / 45% (9) / 55% (soft)
//   split (non-aces)  : play as a total       35% (40% for 8,8 vs 9/10/A)
//   A,A always split · 10,10 always stand
function mulberry32(seed){
  let a = seed >>> 0;
  return function(){
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
function hashSeed(...parts){
  let h = 0x811c9dc5;
  for (const p of parts){ h ^= (p >>> 0); h = Math.imul(h, 0x01000193); h ^= h >>> 13; }
  return h >>> 0;
}
function makeReasonableDecide(rng){
  function core(cards, up, canD, canS){
    let base = strategy(cards, up, canD, canS, true);
    const [t, soft] = total(cards);
    if (base === 'P'){
      const r = RANKVAL[cards[0]];
      if (r === 11) return 'P';                       // everyone splits aces
      const pSkip = (r === 8 && up >= 9) ? 0.40 : 0.35;
      if (rng() < pSkip) return core(cards, up, canD, false);  // play it as a total
      return 'P';
    }
    if (base === 'D'){
      const pSkip = soft ? 0.55 : t === 9 ? 0.45 : 0.30;
      if (rng() < pSkip) base = 'H';
    }
    if (base === 'H'){
      if (!soft){
        if (t === 16 && up >= 9 && rng() < 0.45) return 'S';
        if (t === 15 && up >= 10 && rng() < 0.35) return 'S';
        if (t === 12 && (up === 2 || up === 3) && rng() < 0.30) return 'S';
      } else if (t === 18 && up >= 9 && rng() < 0.50) return 'S';
    }
    if (base === 'S' && !soft && t === 12 && up >= 4 && up <= 6 && rng() < 0.25) return 'H';
    return base;
  }
  return core;
}
// Bet models beyond the flat-$100 book baseline:
//   mix  — each round pick uniformly among the affordable chips {200, 350, 500}
//          (lowest floors to bankroll when short, like the game's chip row)
//   500  — flat $500 every round (floored to bankroll)
const CHIPS_MIX = [200, 350, 500];
function makeBetMix(rng){
  return bk => {
    const aff = CHIPS_MIX.filter(c => c <= bk);
    if (!aff.length) return Math.min(bk, CHIPS_MIX[0]);
    return aff[Math.floor(rng() * aff.length)];
  };
}
const bet500 = bk => Math.min(500, bk);

// ── Daily Missions mission types (daily_missions_economy_spec_v2.md) ──
// Per-round event counts on a play-through log. Definitions:
//   winUnderdogStart  — start hard 12-16 vs dealer 9/10/A, hand wins (no split)
//   winDealerBustLowHand — dealer busts while a winning hand stands on ≤16
//   winSoftHand       — winning hand whose final total is soft
const isWin = h => /WIN/.test(h.res);
const MTYPES = [
  ['m_dd',      r => r.hands.filter(h => h.acts.some(a => a.startsWith('double'))).length],
  ['m_split',   r => r.hands.length === 2 ? 1 : 0],
  ['m_splitdbl',r => (r.hands.length === 2 &&
                      r.hands.some(h => h.acts.some(a => a.startsWith('double')))) ? 1 : 0],
  ['m_win3c',   r => r.hands.filter(h => isWin(h) && h.cards.length >= 3).length],
  ['m_winsoft', r => r.hands.filter(h => { const [t, sft] = total(h.cards);
                      return isWin(h) && sft && t <= 21; }).length],
  ['m_winudog', r => { if (r.hands.length !== 1 || !r.deal) return 0;
                      const st = total([r.deal[0], r.deal[1]]);
                      return (!st[1] && st[0] >= 12 && st[0] <= 16 &&
                        RANKVAL[r.deal[2]] >= 9 && isWin(r.hands[0])) ? 1 : 0; }],
  ['m_windbust',r => { const dt = total(r.dealer)[0]; if (dt <= 21) return 0;
                      return r.hands.filter(h => isWin(h) && total(h.cards)[0] <= 16).length; }],
  ['m_winboth', r => (r.hands.length === 2 && r.hands.every(isWin)) ? 1 : 0],
];

// Weighted KPIs = mean over RUNS seeded stochastic play-throughs (+ std where useful).
// Each run plays the deck three times — flat $100, chip-mix, flat $500 — with the
// SAME decision seed, so bet size is the only thing that differs at the start.
function simulateEnsemble(cardsStr, deckId, runs){
  const seq = cardsStr.split('');
  const acc = {pw:0, dw:0, push:0, pbj:0, dbj:0, p21:0, d21:0, pbust:0, dbust:0,
    splits:0, doubles:0, book:0};
  const winPcts = [], books = [], booksMix = [], books500 = [];
  let bustMix = 0, bust500 = 0;
  const mAcc = new Array(MTYPES.length).fill(0);
  let matchWins = 0;
  const seedBase = hashSeed(Number(BigInt(deckId) & 0xffffffffn), Number(BigInt(deckId) >> 32n));
  for (let k = 0; k < runs; k++){
    const dSeed = hashSeed(0x5EED, seedBase, k);
    const runLog = [];
    const s = gameRoundsFrom(seq, 0, START_BANKROLL, freshStats(),
      makeReasonableDecide(mulberry32(dSeed)), null, runLog);
    MTYPES.forEach(([_, f], i) => runLog.forEach(r => { mAcc[i] += f(r); }));
    if (s.book_final > START_BANKROLL) matchWins++;
    acc.pw += s.player_wins; acc.dw += s.dealer_wins; acc.push += s.pushes;
    acc.pbj += s.player_bj; acc.dbj += s.dealer_bj;
    acc.p21 += s.player_21_3plus; acc.d21 += s.dealer_21_3plus;
    acc.pbust += s.player_busts; acc.dbust += s.dealer_busts;
    acc.splits += s.splits; acc.doubles += s.doubles; acc.book += s.book_final;
    const dec = s.player_wins + s.dealer_wins;
    winPcts.push(dec ? 100 * s.player_wins / dec : 0);
    books.push(s.book_final);
    const sMix = gameRoundsFrom(seq, 0, START_BANKROLL, freshStats(),
      makeReasonableDecide(mulberry32(dSeed)),
      makeBetMix(mulberry32(hashSeed(0xBE7, seedBase, k))));
    booksMix.push(sMix.book_final);
    if (sMix.book_final <= 0) bustMix++;
    const s500 = gameRoundsFrom(seq, 0, START_BANKROLL, freshStats(),
      makeReasonableDecide(mulberry32(dSeed)), bet500);
    books500.push(s500.book_final);
    if (s500.book_final <= 0) bust500++;
  }
  const mean = a => a.reduce((x, y) => x + y, 0) / a.length;
  const std = a => { const m = mean(a); return Math.sqrt(mean(a.map(v => (v - m) * (v - m)))); };
  const r2 = v => +(v / runs).toFixed(2);
  return {
    sim_win_pct: +mean(winPcts).toFixed(1), sim_win_std: +std(winPcts).toFixed(1),
    sim_pw: r2(acc.pw), sim_dw: r2(acc.dw), sim_push: r2(acc.push),
    sim_pbj: r2(acc.pbj), sim_dbj: r2(acc.dbj),
    sim_p21: r2(acc.p21), sim_d21: r2(acc.d21),
    sim_pbust: r2(acc.pbust), sim_dbust: r2(acc.dbust),
    sim_book: Math.round(mean(books)), sim_book_std: Math.round(std(books)),
    sim_mix_book: Math.round(mean(booksMix)), sim_mix_std: Math.round(std(booksMix)),
    sim_mix_bust: +(100 * bustMix / runs).toFixed(1),
    sim_500_book: Math.round(mean(books500)), sim_500_std: Math.round(std(books500)),
    sim_500_bust: +(100 * bust500 / runs).toFixed(1),
    ...Object.fromEntries(MTYPES.map(([k], i) => [k, r2(mAcc[i])])),
    m_matchwin: +(100 * matchWins / runs).toFixed(1),
  };
}

// ── main ──
// Input: either the original array-of-objects JSON, or an existing
// deck_stats.json ({fields, rows}) — so re-runs respect deleted decks.
const input = process.argv[2] || path.join(__dirname, 'deck_stats.json');
const runsArg = process.argv.indexOf('--runs');
const RUNS = runsArg > -1 ? +process.argv[runsArg + 1] : 200;
let src = JSON.parse(fs.readFileSync(input, 'utf8'));
const decks = Array.isArray(src) ? src
  : src.rows.map(r => Object.fromEntries(src.fields.map((f, i) => [f, r[i]])));
console.log(`Simulating ${decks.length} decks — book line + ${RUNS} weighted "reasonable player" runs each…`);

const STAT_KEYS = ['rounds','player_bj','dealer_bj','splits','doubles','pairs_dealt',
  'player_wins','dealer_wins','pushes','dealer_21_3plus','player_21_3plus',
  'dealer_busts','player_busts','hands_played','cards_used','book_final'];
const SIM_KEYS = ['sim_win_pct','sim_win_std','sim_pw','sim_dw','sim_push','sim_pbj','sim_dbj',
  'sim_p21','sim_d21','sim_pbust','sim_dbust','sim_book','sim_book_std',
  'sim_mix_book','sim_mix_std','sim_mix_bust','sim_500_book','sim_500_std','sim_500_bust',
  'm_dd','m_split','m_splitdbl','m_win3c','m_winsoft','m_winudog','m_windbust','m_winboth','m_matchwin'];
const DECK_KEYS = ['deck_id','cards','optimal_final','tier','fun_raw','fun_pct','mean_std','skill_noise'];

const t0 = Date.now();
const rows = decks.map((d, i) => {
  const st = playDeck(d.cards);
  const sim = simulateEnsemble(d.cards, d.deck_id, RUNS);
  if (i % 5000 === 4999) console.log(`  ${i + 1}/${decks.length}…`);
  return [...DECK_KEYS.map(k => d[k]), ...STAT_KEYS.map(k => st[k]), ...SIM_KEYS.map(k => sim[k])];
});
console.log(`Done in ${((Date.now() - t0) / 1000).toFixed(1)}s`);

const out = {fields: [...DECK_KEYS, ...STAT_KEYS, ...SIM_KEYS],
  rules: 'classic-game-flow S17', sim_runs: RUNS, rows};
const dir = __dirname;
fs.writeFileSync(path.join(dir, 'deck_stats.json'), JSON.stringify(out));
fs.writeFileSync(path.join(dir, 'data.js'), 'window.DECK_DATA=' + JSON.stringify(out) + ';');
console.log('Wrote data.js and deck_stats.json');

// quick aggregate sanity print
const idx = Object.fromEntries(out.fields.map((f, i) => [f, i]));
const sum = k => rows.reduce((a, r) => a + r[idx[k]], 0);
const pw = sum('player_wins'), dw = sum('dealer_wins');
console.log({decks: rows.length, rounds: sum('rounds'), player_bj: sum('player_bj'),
  dealer_bj: sum('dealer_bj'), pushes: sum('pushes'), player_wins: pw, dealer_wins: dw,
  pd_ratio: +(pw / dw).toFixed(4), dealer_21_3plus: sum('dealer_21_3plus'),
  player_21_3plus: sum('player_21_3plus'), avg_book_final: Math.round(sum('book_final') / rows.length),
  avg_sim_win_pct: +(sum('sim_win_pct') / rows.length).toFixed(1),
  avg_sim_book: Math.round(sum('sim_book') / rows.length)});
