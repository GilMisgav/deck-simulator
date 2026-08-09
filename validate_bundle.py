#!/usr/bin/env python3
"""
Validate a Missions bundle (PRD validation rules) with expression-syntax conditions.

Conditions are authored as text expressions, e.g.
    level >= 3 && country in ("US","CA") && installed_at < 09:00 GMT
`openingCondition` no longer exists - the threshold lives in the condition itself.
"""
import hashlib, json, re, sys

BANK = {
 "open_any_pair","open_mixed_pair","open_colored_pair","open_same_suit","open_same_color",
 "open_blackjack","open_suited_blackjack","open_pocket_aces","open_hard_20","open_start_11",
 "plus3_pair","plus3_flush","plus3_straight","plus3_trips","plus3_straight_flush",
 "four_two_pair","four_trips","four_flush","four_straight","four_straight_flush","four_quads",
 "reach_21","win_5plus_cards","win_6plus_cards","win_after_double","win_split_hand",
 "dealer_bust","dealer_bust_5plus","dealer_bust_6plus",
}
assert len(BANK) == 29

# ---------------------------------------------------------------- UID contract
#   bundleUid   bnd.<personal|calendric>.<YYYYMMDD>.<NN>
#   configUid   cfg.<personal|calendric>.<slug>        (configType is NOT encoded:
#                 it is recoverable from ChainServed.selection and Defined.config_type,
#                 and encoding it would force a rename on a scripted<->random switch)
#   chainUid    chn.<composition_id>            content address of the experience
#   missionUid  msn.<composition_id>.<mission_type>
#   tierUid     tier.<config_slug>.<n>
# Each UID restates facts held elsewhere in the file, so a copy-paste that leaves a
# UID disagreeing with its own content is rejected instead of shipping.
SLUG = r"[a-z0-9]+(?:_[a-z0-9]+)*"
RE_BUNDLE  = re.compile(rf"^bnd\.(personal|calendric)\.(\d{{8}})\.(\d{{2}})$")
RE_CONFIG  = re.compile(rf"^cfg\.(personal|calendric)\.({SLUG})$")
RE_CHAIN   = re.compile(r"^chn\.([0-9a-f]{8})$")
RE_TIER    = re.compile(rf"^tier\.({SLUG})\.(\d+)$")

def composition_id(missions):
    """Content address of a chain: its ordered mission TYPES, hashed.
       Types only - so retuning targets or rewards never churns the id.
       Order is included because it is the serve sequence."""
    ordered = [m.get("type") for m in sorted(missions, key=lambda x: x.get("index", 0))]
    return hashlib.sha1("|".join(map(str, ordered)).encode()).hexdigest()[:8]

def derive_chain_uid(missions):
    return f"chn.{composition_id(missions)}"

def derive_mission_uid(comp_id, mission_type):
    return f"msn.{comp_id}.{mission_type}"

def check_uids(cfgjson, e):
    btype = cfgjson.get("bundleType")
    bu    = cfgjson.get("bundleUid", "")
    mb = RE_BUNDLE.match(bu or "")
    if not mb:
        e.append(f"UID bundleUid '{bu}' must be bnd.<personal|calendric>.<YYYYMMDD>.<NN>")
    elif mb.group(1) != btype:
        e.append(f"UID bundleUid says '{mb.group(1)}' but bundleType is '{btype}'")

    for cu, c in cfgjson.get("configs", {}).items():
        mc = RE_CONFIG.match(cu)
        if not mc:
            e.append(f"UID configUid '{cu}' must be cfg.<bundleType>.<slug>")
            continue
        c_btype, c_slug = mc.groups()
        if c_btype != btype:
            e.append(f"UID {cu}: encodes '{c_btype}' but bundle is '{btype}'")

        for ck, ch in c.get("chains", {}).items():
            mk = RE_CHAIN.match(ck)
            if not mk:
                e.append(f"UID chainUid '{ck}' must be chn.<8-hex composition id>"); continue
            want_ck = derive_chain_uid(ch.get("missions", []))
            if ck != want_ck:
                e.append(f"UID chainUid '{ck}' does not match its own composition - "
                         f"should be '{want_ck}' for [{' > '.join(m.get('type','?') for m in sorted(ch.get('missions',[]), key=lambda x: x.get('index',0)))}]")
            comp = mk.group(1)
            for m in ch.get("missions", []):
                want = derive_mission_uid(comp, m.get("type"))
                if m.get("missionUid") != want:
                    e.append(f"UID missionUid '{m.get('missionUid')}' should be '{want}' "
                             f"(chain composition id + mission type)")

        for i, t in enumerate(c.get("progression", {}).get("tiers", []), start=1):
            mt = RE_TIER.match(t.get("tierUid",""))
            if not mt:
                e.append(f"UID tierUid '{t.get('tierUid')}' must be tier.<config_slug>.<n>"); continue
            if mt.group(1) != c_slug:
                e.append(f"UID {t['tierUid']}: config slug != '{c_slug}'")
            if int(mt.group(2)) != i:
                e.append(f"UID {t['tierUid']}: number should be {i} (its position in tiers)")

# field -> type
FIELDS = {
    "level": "number", "matches_total": "number", "matches_per_game": "number",
    "days_in_app": "number", "minutes_since_install": "duration",
    "installed_at": "datetime", "country": "text",
    "is_registered": "bool", "spend_tier": "text",
}
SPEND = {"none", "minnow", "dolphin", "whale"}
ORDERED = {">", ">=", "<", "<="}          # number, duration, datetime only
EQ      = {"==", "!="}                    # any type
MEMBER  = {"in", "not in"}                # number, text only
ORDERED_TYPES = {"number", "duration", "datetime"}
MEMBER_TYPES  = {"number", "text"}
# a duration literal is accepted wherever a plain number is (converted to the field's unit)
COMPATIBLE = {
    "number":   {"number", "duration"},
    "duration": {"duration", "number"},
    "datetime": {"datetime", "time"},
    "text":     {"text"},
    "bool":     {"bool"},
}

TOKENS = [
    ("WS",       r"\s+"),
    ("STRING",   r'"[^"]*"|\'[^\']*\''),
    ("DATETIME", r"\d{4}-\d{2}-\d{2}(?:[ T]\d{1,2}:\d{2})?(?:\s*(?:GMT|UTC|Z))?"),
    ("TIME",     r"\d{1,2}:\d{2}(?:\s*(?:GMT|UTC|Z))?"),
    ("DURATION", r"(?:\d+[dhms])+(?![\w:])"),
    ("NUMBER",   r"-?\d+(?:\.\d+)?"),
    ("OP2",      r"&&|\|\||>=|<=|==|!="),
    ("NOTIN",    r"\bnot\s+in\b"),
    ("IN",       r"\bin\b"),
    ("BOOL",     r"\btrue\b|\bfalse\b"),
    ("IDENT",    r"[A-Za-z_][A-Za-z0-9_]*"),
    ("PUNCT",    r"[()!<>,]"),
]
MASTER = re.compile("|".join(f"(?P<{n}>{p})" for n, p in TOKENS))

LIT_TYPE = {"STRING": "text", "NUMBER": "number", "DURATION": "duration",
            "DATETIME": "datetime", "TIME": "time", "BOOL": "bool"}

def tokenize(expr, path, e):
    toks, pos = [], 0
    while pos < len(expr):
        m = MASTER.match(expr, pos)
        if not m:
            e.append(f"R15 {path}: unparseable character '{expr[pos]}' at position {pos}")
            return None
        kind = m.lastgroup
        if kind != "WS":
            toks.append((kind, m.group().strip(), m.start()))
        pos = m.end()
    return toks

def validate_expression(expr, path, e):
    if not isinstance(expr, str) or not expr.strip():
        e.append(f"R15 {path}: condition is required and must be a non-empty expression")
        return
    if expr.strip().lower() in ("true", "1"):
        e.append(f"R15 {path}: condition must not match everyone (literal 'true' is rejected) "
                 f"- it would shadow every lower-priority segment")
        return
    toks = tokenize(expr, path, e)
    if toks is None:
        return

    depth = 0
    for kind, text, at in toks:
        if text == "(": depth += 1
        elif text == ")":
            depth -= 1
            if depth < 0:
                e.append(f"R15 {path}: unbalanced ')' at position {at}"); return
    if depth:
        e.append(f"R15 {path}: unbalanced parentheses (missing {depth} closing)")

    # every bare identifier must be a known field
    for kind, text, at in toks:
        if kind == "IDENT" and text not in FIELDS:
            near = ", ".join(sorted(FIELDS))
            e.append(f"R15 {path}: unknown field '{text}' at position {at} - available: {near}")

    # each comparison: field <op> literal / list
    i = 0
    compared = set()
    while i < len(toks):
        kind, text, at = toks[i]
        if kind == "IDENT" and text in FIELDS:
            if i + 1 >= len(toks):
                e.append(f"R15 {path}: field '{text}' at position {at} has no comparison"); break
            ftype = FIELDS[text]
            op = toks[i+1][1] if toks[i+1][0] in ("OP2","IN","NOTIN") else toks[i+1][1]
            op = re.sub(r"\s+", " ", op)
            if toks[i+1][0] == "PUNCT" and op in ("<", ">"):
                pass
            elif toks[i+1][0] not in ("OP2", "IN", "NOTIN"):
                e.append(f"R15 {path}: field '{text}' at position {at} is not compared to anything "
                         f"(found '{toks[i+1][1]}') - a bare field is not a condition")
                i += 1; continue
            compared.add(text)
            if op in ORDERED and ftype not in ORDERED_TYPES:
                e.append(f"R15 {path}: operator '{op}' needs number/duration/datetime, "
                         f"but '{text}' holds {ftype}")
            if op in MEMBER and ftype not in MEMBER_TYPES:
                e.append(f"R15 {path}: operator '{op}' needs number/text, but '{text}' holds {ftype}")
            # operand
            j = i + 2
            if op in MEMBER:
                if j >= len(toks) or toks[j][1] != "(":
                    e.append(f"R15 {path}: '{op}' after '{text}' needs a list like (\"US\", \"CA\")")
                else:
                    j += 1
                    vals = []
                    while j < len(toks) and toks[j][1] != ")":
                        if toks[j][0] in LIT_TYPE: vals.append(toks[j])
                        j += 1
                    if not vals:
                        e.append(f"R15 {path}: empty list after '{op}' on '{text}'")
                    for k, t, a in vals:
                        if LIT_TYPE[k] not in COMPATIBLE[ftype]:
                            e.append(f"R15 {path}: '{text}' ({ftype}) compared against "
                                     f"{LIT_TYPE[k]} '{t}' at position {a}")
                        if text == "spend_tier" and t.strip('"\'').lower() not in SPEND:
                            e.append(f"R15 {path}: spend_tier value {t} not in {sorted(SPEND)}")
            else:
                if j >= len(toks) or toks[j][0] not in LIT_TYPE:
                    e.append(f"R15 {path}: '{text} {op}' is missing a value")
                else:
                    k, t, a = toks[j]
                    if LIT_TYPE[k] not in COMPATIBLE[ftype]:
                        e.append(f"R15 {path}: '{text}' ({ftype}) compared against "
                                 f"{LIT_TYPE[k]} '{t}' at position {a}")
                    if text == "spend_tier" and t.strip('"\'').lower() not in SPEND:
                        e.append(f"R15 {path}: spend_tier value {t} not in {sorted(SPEND)}")
            i = j
        i += 1
    if not compared:
        e.append(f"R15 {path}: no valid field comparison found in condition")

LEVEL_GATE = re.compile(r"^\s*level\s*(>=|>)\s*(\d+)\s*$")

def _simple_level_gate(cond):
    """If the whole condition is just 'level >=/> N', return the effective minimum."""
    if not isinstance(cond, str): return None
    m = LEVEL_GATE.match(cond)
    if not m: return None
    v = int(m.group(2))
    return v if m.group(1) == ">=" else v + 1

def check_reachability(segs, e):
    """First match wins: a segment is dead if a lower-priority one always matches it too."""
    ordered = sorted([s for s in segs if "priority" in s], key=lambda x: x["priority"])
    for i, lower in enumerate(ordered):
        for higher in ordered[:i]:
            if str(higher.get("condition","")).strip() == str(lower.get("condition","")).strip():
                e.append(f"UNREACHABLE segment '{lower.get('segmentUid')}' (priority {lower['priority']}) "
                         f"has the same condition as '{higher.get('segmentUid')}' "
                         f"(priority {higher['priority']}) - first match wins, so it never fires")
                continue
            hi, lo = _simple_level_gate(higher.get("condition")), _simple_level_gate(lower.get("condition"))
            if hi is not None and lo is not None and hi <= lo:
                e.append(f"UNREACHABLE segment '{lower.get('segmentUid')}' (priority {lower['priority']}, "
                         f"level>={lo}) is shadowed by '{higher.get('segmentUid')}' "
                         f"(priority {higher['priority']}, level>={hi}) - the broader gate is evaluated first")

def check_segment(s, btype, configs, e):
    su = s.get("segmentUid")
    if s.get("configUid") not in configs:
        e.append(f"R9 segment {su} -> missing config {s.get('configUid')}")
    if "priority" not in s:
        e.append(f"R10 segment {su} missing priority")
    if "conditions" in s:
        e.append(f"R15 segment {su}: 'conditions' (JSON tree) was replaced by 'condition' (expression)")
    if "openingCondition" in s:
        e.append(f"R14 segment {su}: 'openingCondition' no longer exists - fold the threshold "
                 f"into 'condition' instead")
    validate_expression(s.get("condition"), f"segments['{su}'].condition", e)

def validate(path, strict_uids=False):
    cfg = json.load(open(path)); e = []
    if strict_uids: check_uids(cfg, e)
    btype   = cfg.get("bundleType")
    segs    = cfg.get("segments", [])
    configs = cfg.get("configs", {})

    if "miniCurrency" in cfg:
        e.append("miniCurrency present - mission_token is hard-coded, must not be in the JSON")

    seg_uids, prios = set(), []
    for s in segs:
        su = s.get("segmentUid")
        if su in seg_uids: e.append(f"R9 duplicate segmentUid {su}")
        seg_uids.add(su)
        if "priority" in s: prios.append(s["priority"])
        check_segment(s, btype, configs, e)
    if len(prios) != len(set(prios)):
        e.append(f"R10 priorities not unique: {prios}")
    check_reachability(segs, e)
    for k in configs:
        if not any(s.get("configUid") == k for s in segs):
            e.append(f"R9 orphan config {k} (no segment references it)")

    all_uids = {"chain": set(), "mission": set(), "tier": set()}
    for cu, c in configs.items():
        if c.get("configUid") != cu: e.append(f"R3 {cu}: key != configUid")
        ctype = c.get("configType")
        cap = c.get("dailyMissions", {}).get("dailyCap")
        vis = c.get("dailyMissions", {}).get("visibleSlots")
        if vis and cap and vis > cap: e.append(f"{cu}: visibleSlots > dailyCap")

        if btype == "personal":
            if "personal" not in c.get("timing", {}): e.append(f"R6 {cu}: personal needs timing.personal")
            if "prorationCalendricFirstExposure" in c: e.append(f"R13 {cu}: personal must omit proration")
            if "openingCondition" in c.get("timing", {}).get("personal", {}):
                e.append(f"R14 {cu}: timing.personal.openingCondition no longer exists")
        else:
            if "timing" in c: e.append(f"R6 {cu}: calendric must omit timing")
            p = c.get("prorationCalendricFirstExposure")
            if not p: e.append(f"R13 {cu}: calendric needs proration block")
            else:
                if "scope" in p: e.append(f"R13 {cu}: proration must not carry scope")
                if "minReward" not in p: e.append(f"R13 {cu}: proration missing minReward")

        has_rot, has_pool = "rotation" in c, "pool" in c
        if ctype == "scripted" and (not has_rot or has_pool or "noRepeatDays" in c):
            e.append(f"R12 {cu}: scripted must have rotation only")
        if ctype == "random" and (not has_pool or has_rot):
            e.append(f"R12 {cu}: random must have pool only")

        chains = c.get("chains", {})
        cfg_chain_uids, cfg_mission_uids = set(), set()
        for k, ch in chains.items():
            if ch.get("chainUid") != k: e.append(f"R3 {cu}/{k}: chains key != chainUid")
            if k in cfg_chain_uids: e.append(f"R3 duplicate chainUid {k} within {cu}")
            cfg_chain_uids.add(k)
            ms = ch.get("missions", [])
            if len(ms) != cap: e.append(f"R4 {cu}/{k}: {len(ms)} missions, dailyCap={cap}")
            idx = sorted(m.get("index") for m in ms)
            if idx and idx != list(range(1, len(ms)+1)):
                e.append(f"R4 {cu}/{k}: indices {idx} not 1..{len(ms)}")
            for m in ms:
                mu = m.get("missionUid")
                if mu in cfg_mission_uids: e.append(f"R3 duplicate missionUid {mu} within {cu}")
                cfg_mission_uids.add(mu)
                if m.get("type") not in BANK:
                    e.append(f"{cu}/{k}/{mu}: type '{m.get('type')}' not in 29-mission bank")
                r = m.get("reward", {})
                if "mission_token" not in r: e.append(f"R5 {mu}: missing mission_token")
                if "sku" in r: e.append(f"R5 {mu}: sku not permitted")
                if "bonusCash" in r and not (r["bonusCash"] > 0):
                    e.append(f"R5 {mu}: bonusCash must be positive")

        dur = (c.get("timing", {}).get("personal", {}).get("durationDays")
               or c.get("progression", {}).get("numberOfDays"))
        if ctype == "scripted":
            rot = c.get("rotation", [])
            if dur and len(rot) < dur: e.append(f"R1 {cu}: rotation has {len(rot)} chains for {dur} days")
            for r in rot:
                if r not in chains: e.append(f"R2 {cu}: rotation ref '{r}' not in chains")
        else:
            pool = c.get("pool", [])
            for pi in pool:
                if pi.get("chainUid") not in chains:
                    e.append(f"R2 {cu}: pool ref '{pi.get('chainUid')}' not in chains")
            nrd = c.get("noRepeatDays")
            if nrd is None or not (0 <= nrd < len(pool)):
                e.append(f"R8 {cu}: noRepeatDays={nrd} must be >=0 and < pool size {len(pool)}")

        pr = c.get("progression", {}); tiers = pr.get("tiers", [])
        if not (2 <= len(tiers) <= 5): e.append(f"R11 {cu}: {len(tiers)} chests, must be 2-5")
        prev = None
        for t in tiers:
            tu = t.get("tierUid")
            if tu in all_uids["tier"]: e.append(f"R3 duplicate tierUid {tu}")
            all_uids["tier"].add(tu)
            tr = t.get("tokensRequired")
            if prev is not None and tr <= prev:
                e.append(f"R7 {cu}: tokensRequired not strictly increasing at {tu}")
            prev = tr
            if "mission_token" in t.get("reward", {}):
                e.append(f"{cu}/{tu}: chest reward must be bonus cash only")
        if btype == "personal" and pr.get("numberOfDays") != c.get("timing",{}).get("personal",{}).get("durationDays"):
            e.append(f"R7 {cu}: numberOfDays != durationDays")
    return e

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--uids"]
    strict = "--uids" in sys.argv
    bad = 0
    for path in args:
        errs = validate(path, strict_uids=strict)
        print(f"\n=== {path.split('/')[-1]} ===")
        if errs:
            bad = 1
            for x in errs: print(f"  FAIL {x}")
            print(f"  -> {len(errs)} issue(s)")
        else:
            print("  PASS")
    sys.exit(bad)
