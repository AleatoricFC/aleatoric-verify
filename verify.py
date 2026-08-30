#!/usr/bin/env python3
"""
Offline auditor for the AleatoricFC public bet record.

Most people never need this — just open the web page, which runs the same checks
in your browser. This script is for anyone who wants to confirm everything from
scratch, offline, trusting nothing but the pinned public key.

    pip install cryptography
    python verify.py                 # verify every day + the whole chain
    python verify.py 2026-08-30      # verify a single day

It checks, for each day:
  1. the Ed25519 signature over {sha256, timestamp}  (locked by the private key)
  2. the revealed bets.json hashes to exactly what was signed  (unaltered)
  3. the revealed bets cover exactly the pre-committed manifest fixtures
  4. the day links to the previous one  (append-only chain)
and that the final chain head matches the value pinned in the Telegram bio.
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


def chain_hash(prev, date, m_sha, b_sha, sig):
    return hashlib.sha256("|".join([prev, date, m_sha, b_sha, sig]).encode()).hexdigest()


def verify_day(pub, entry, prev):
    d = entry["date"]
    day = ROOT / "data" / d
    failures = 0
    print(f"\n── {d} ─────────────────────────────────────────")

    manifest_bytes = (day / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)

    payload = json.dumps({"sha256": entry["bets_sha256"], "timestamp": entry["timestamp"]},
                         sort_keys=True).encode()
    try:
        pub.verify(base64.b64decode(entry["signature"]), payload)
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

    return failures, link


def main():
    index = json.loads((ROOT / "index.json").read_text())
    pub = serialization.load_pem_public_key(index["public_key_pem"].encode())

    only = sys.argv[1] if len(sys.argv) > 1 else None
    total_fail = 0
    prev = GENESIS
    for entry in index["days"]:
        f, prev = verify_day(pub, entry, prev) if (only is None or entry["date"] == only) \
            else (0, chain_hash(prev, entry["date"], entry["manifest_sha256"],
                                entry["bets_sha256"], entry["signature"]))
        total_fail += f

    print("\n── chain head ─────────────────────────────────────")
    if prev == index["head"]:
        ok(f"head {prev[:16]}… matches — full history intact")
    else:
        bad("computed head does not match index — tampering"); total_fail += 1

    print()
    if total_fail == 0:
        print(f"{GREEN}ALL CHECKS PASSED{RST}")
    else:
        print(f"{RED}{total_fail} CHECK(S) FAILED{RST}"); sys.exit(1)


if __name__ == "__main__":
    main()
