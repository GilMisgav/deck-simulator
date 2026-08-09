#!/usr/bin/env python3
"""
Stamp every UID in a Missions bundle from its content, so none are hand-typed.

    python build_uids.py draft.json out.json [--date YYYYMMDD] [--seq NN]

The input needs the content but not the identifiers:

  - bundleType                      personal | calendric
  - configs keyed by ANY handle     the handle becomes the config slug
  - each config: configType, dailyMissions, chains, progression, timing/proration
  - chains keyed by ANY handle      handles are discarded; chains are content-addressed
  - each mission: index, type, target, reward
  - segments: label, priority, condition, and configUid naming a config handle

Everything below is then derived:

  bundleUid   bnd.<bundleType>.<date>.<seq>
  configUid   cfg.<bundleType>.<config slug>
  chainUid    chn.<8-hex sha1 of ordered mission types>
  missionUid  msn.<composition id>.<mission type>
  tierUid     tier.<config slug>.<1-based position>

Re-running is safe and idempotent: already-stamped bundles come out identical,
so use it after any content edit to bring identifiers back in line.
"""
import argparse
import datetime
import hashlib
import json
import re
import sys

def composition_id(missions):
    """Content address of a chain: its ordered mission TYPES.

    Types only, so retuning a target or reward never changes a chain's identity.
    Order is included because it is the serve sequence.
    """
    ordered = [m.get("type") for m in sorted(missions, key=lambda x: x.get("index", 0))]
    return hashlib.sha1("|".join(map(str, ordered)).encode()).hexdigest()[:8]

def slugify(handle):
    """Reduce an authored handle to a slug: lowercase, underscores only."""
    s = re.sub(r"[^a-z0-9]+", "_", str(handle).lower()).strip("_")
    # strip any prefix a previous stamping added, e.g. cfg.personal.qa_main -> qa_main
    return s.split("_")[-1] if s.startswith(("cfg_", "chn_", "bnd_")) else s

def config_slug(handle):
    if handle.startswith("cfg."):
        return handle.split(".")[-1]
    return slugify(handle)

def stamp(bundle, date=None, seq="01"):
    btype = bundle.get("bundleType")
    if btype not in ("personal", "calendric"):
        sys.exit(f"bundleType must be 'personal' or 'calendric', got {btype!r}")

    date = date or datetime.date.today().strftime("%Y%m%d")
    bundle["bundleUid"] = f"bnd.{btype}.{date}.{seq}"

    handle_to_uid, new_configs = {}, {}
    for handle, cfg in bundle.get("configs", {}).items():
        slug = config_slug(handle)
        cuid = f"cfg.{btype}.{slug}"
        handle_to_uid[handle] = cuid
        cfg["configUid"] = cuid

        # chains: content-addressed, so the authored handle is discarded
        chains, chain_map = {}, {}
        for chandle, chain in cfg.get("chains", {}).items():
            missions = chain.get("missions", [])
            comp = composition_id(missions)
            cuid_chain = f"chn.{comp}"
            if cuid_chain in chains:
                sys.exit(f"{cuid} has two chains with identical composition "
                         f"({chandle} collides with an earlier chain) - "
                         f"a duplicate experience should be one chain, not two")
            chain_map[chandle] = cuid_chain
            chain["chainUid"] = cuid_chain
            for m in missions:
                m["missionUid"] = f"msn.{comp}.{m.get('type')}"
                for k in ("missionUid", "index", "type", "target", "reward"):
                    if k in m:
                        m[k] = m.pop(k)          # stable key order
            for k in ("chainUid", "label", "missions"):
                if k in chain:
                    chain[k] = chain.pop(k)
            chains[cuid_chain] = chain
        cfg["chains"] = chains

        # rewrite chain references
        if "rotation" in cfg:
            cfg["rotation"] = [chain_map.get(x, x) for x in cfg["rotation"]]
        if "pool" in cfg:
            for entry in cfg["pool"]:
                h = entry.get("chainUid", entry.get("chain"))
                entry.pop("chain", None)
                entry["chainUid"] = chain_map.get(h, h)

        for i, tier in enumerate(cfg.get("progression", {}).get("tiers", []), start=1):
            tier["tierUid"] = f"tier.{slug}.{i}"
            for k in ("tierUid", "tokensRequired", "reward"):
                if k in tier:
                    tier[k] = tier.pop(k)

        new_configs[cuid] = cfg
    bundle["configs"] = new_configs

    for seg in bundle.get("segments", []):
        h = seg.get("configUid")
        if h not in handle_to_uid and h not in new_configs:
            sys.exit(f"segment {seg.get('segmentUid')} references unknown config {h!r}")
        seg["configUid"] = handle_to_uid.get(h, h)
        for k in ("segmentUid", "label", "priority", "configUid", "condition"):
            if k in seg:
                seg[k] = seg.pop(k)

    for k in ("version", "bundleUid", "bundleType", "segments", "configs"):
        if k in bundle:
            bundle[k] = bundle.pop(k)
    return bundle

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("infile")
    ap.add_argument("outfile")
    ap.add_argument("--date", help="YYYYMMDD for bundleUid (default: today)")
    ap.add_argument("--seq", default="01", help="two-digit sequence (default 01)")
    a = ap.parse_args()

    with open(a.infile) as f:
        bundle = json.load(f)
    stamp(bundle, a.date, a.seq)
    with open(a.outfile, "w") as f:
        json.dump(bundle, f, indent=2)
        f.write("\n")

    print(f"{a.outfile}")
    print(f"  bundleUid  {bundle['bundleUid']}")
    for cuid, cfg in bundle["configs"].items():
        chains = cfg.get("chains", {})
        print(f"  {cuid}  ({cfg.get('configType')}, {len(chains)} chains)")
        for ck, ch in chains.items():
            print(f"     {ck}  {ch.get('label','')}")
    print("\nNow validate:  python validate_bundle.py --uids " + a.outfile)

if __name__ == "__main__":
    main()
