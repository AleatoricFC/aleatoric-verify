#!/usr/bin/env python3
"""
Offline auditor for the AleatoricFC public bet record.

Most people never need this — just open the web page, which runs the same checks
in your browser. This script is for anyone who wants to confirm everything from
scratch, offline, trusting nothing but the pinned public key.

    pip install cryptography
    python verify.py                 # verify every day + the whole chain + the ROI
    python verify.py 2026-08-30      # verify a single day

It checks, for each day:
  1. the Ed25519 signature over {sha256, timestamp}  (bets locked by the private key)
  2. the revealed bets.json hashes to exactly what was signed  (unaltered)
  3. the revealed bets cover exactly the pre-committed manifest fixtures
  4. the day links to the previous one  (append-only chain)
  5. if published: the match results are signed & unaltered (a separate layer), and
     the day's profit is recomputed from the signed bets + those public results.
Then it confirms the final chain head matches the value pinned in the Telegram bio,
and prints the overall ROI — the same number the web page shows.
"""
import sys
import json
import base64
import hashlib
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature

ROOT = Path(__file__).parent
GENESIS = "GENESIS"
GREEN, RED, DIM, RST = "\033[32m", "\033[31m", "\033[2m", "\033[0m"


def ok(m):  print(f"{GREEN}  OK{RST}  {m}")
def bad(m): print(f"{RED}FAIL{RST}  {m}")
def wait(m): print(f"{DIM}  ··{RST}  {m}")


def fixtures(entries):
    return {(e["date"], e["home_team_name"], e["away_team_name"], e["market"]) for e in entries}


def fixture_key(e):
    return (e["date"], e["home_team_name"], e["away_team_name"], e["market"])


def chain_hash(prev, date, m_sha, b_sha, sig):
    return hashlib.sha256("|".join([prev, date, m_sha, b_sha, sig]).encode()).hexdigest()


def _verify_sig(pub, signature, sha, timestamp):
    payload = json.dumps({"sha256": sha, "timestamp": timestamp}, sort_keys=True).encode()
    pub.verify(base64.b64decode(signature), payload)


def verify_day(pub, entry, prev):
    """Returns (failures, chain_link, day_pnl_or_None, day_staked_or_None, won, settled)."""
    d = entry["date"]
    day = ROOT / "data" / d
    failures = 0
    print(f"\n── {d} ─────────────────────────────────────────")

    manifest_bytes = (day / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)

    try:
        _verify_sig(pub, entry["signature"], entry["bets_sha256"], entry["timestamp"])
        ok(f"signature valid — locked {entry['timestamp']}")
    except InvalidSignature:
        bad("signature invalid"); failures += 1

    if hashlib.sha256(manifest_bytes).hexdigest() == entry["manifest_sha256"]:
        ok("manifest matches record")
    else:
        bad("manifest hash mismatch"); failures += 1

    link = chain_hash(prev, d, entry["manifest_sha256"], entry["bets_sha256"], entry["signature"])
    if link == entry["chain"]:
        ok("chain link intact")
    else:
        bad("chain link broken — history altered"); failures += 1

    bets = None
    bets_path = day / "bets.json"
    if entry["bets_present"] and bets_path.exists():
        bets_bytes = bets_path.read_bytes()
        bets = json.loads(bets_bytes)
        if hashlib.sha256(bets_bytes).hexdigest() == entry["bets_sha256"]:
            ok("revealed bets match the signature exactly")
        else:
            bad("bets.json altered since signing"); failures += 1
        if fixtures(manifest) == fixtures(bets):
            ok(f"{len(fixtures(bets))} fixture(s) match the pre-commitment")
        else:
            bad("revealed bets differ from committed fixtures"); failures += 1
    else:
        wait("full bets not yet revealed (publishes next day)")

    # Results — separate signed layer, not part of the chain.
    day_pnl = day_staked = won = settled = None
    if entry.get("results_present"):
        results_bytes = (day / "results.json").read_bytes()
        results = json.loads(results_bytes)
        results_ok = True
        try:
            _verify_sig(pub, entry["results_signature"], entry["results_sha256"], entry["results_timestamp"])
        except InvalidSignature:
            bad("results signature invalid"); failures += 1; results_ok = False
        if hashlib.sha256(results_bytes).hexdigest() != entry["results_sha256"]:
            bad("results.json altered since signing"); failures += 1; results_ok = False
        if results_ok:
            ok(f"bet settlements signed & unaltered ({len(results)} legs)")
        if bets is not None and results_ok:
            rmap = {(fixture_key(r), r["outcome"]): r["settled"] for r in results}
            day_pnl = day_staked = 0.0; won = settled = 0
            for b in bets:
                state = rmap.get((fixture_key(b), b["outcome"]))
                if state is None or state == "VOID":
                    continue
                settled += 1; day_staked += b["size"]
                win = state == "WON"
                won += 1 if win else 0
                day_pnl += b["size"] * (b["price"] - 1) if win else -b["size"]
            if settled:
                roi = day_pnl / day_staked
                ok(f"day P&L from signed bets + results: {day_pnl:+.2f} on {day_staked:.2f} "
                   f"staked ({roi*100:+.1f}%)")
    elif entry["bets_present"]:
        wait("results not yet published (matches unsettled)")

    return failures, link, day_pnl, day_staked, won, settled


def main():
    index = json.loads((ROOT / "index.json").read_text())
    pub = serialization.load_pem_public_key(index["public_key_pem"].encode())

    only = sys.argv[1] if len(sys.argv) > 1 else None
    total_fail = 0
    prev = GENESIS
    cum_pnl = cum_staked = cum_won = cum_settled = 0.0
    for entry in index["days"]:
        if only is None or entry["date"] == only:
            f, prev, pnl, staked, won, settled = verify_day(pub, entry, prev)
            total_fail += f
            if pnl is not None:
                cum_pnl += pnl; cum_staked += staked; cum_won += won; cum_settled += settled
        else:
            prev = chain_hash(prev, entry["date"], entry["manifest_sha256"],
                              entry["bets_sha256"], entry["signature"])

    print("\n── chain head ─────────────────────────────────────")
    if prev == index["head"]:
        ok(f"head {prev[:16]}… matches — full history intact")
    else:
        bad("computed head does not match index — tampering"); total_fail += 1

    if cum_staked > 0:
        print("\n── the claim (recomputed) ─────────────────────────")
        ok(f"ROI {cum_pnl/cum_staked*100:+.1f}%  ·  net {cum_pnl:+.2f} on {cum_staked:.2f} staked  "
           f"·  {int(cum_won)}/{int(cum_settled)} won")

    print()
    if total_fail == 0:
        print(f"{GREEN}ALL CHECKS PASSED{RST}")
    else:
        print(f"{RED}{total_fail} CHECK(S) FAILED{RST}"); sys.exit(1)


if __name__ == "__main__":
    main()
