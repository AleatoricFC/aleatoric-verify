#!/usr/bin/env python3
"""
Regenerate index.json and the tamper-evident hash chain from everything in data/.

Run this after adding a new day's files (or after revealing a day's full bets),
then commit + push. The browser verifier (index.html) and the CLI (verify.py)
both read index.json.

The chain makes the whole history append-only: each day links to the previous
day's `chain` value, so a single pinned `head` hash (put it in the Telegram bio)
lets anyone confirm no past day was silently edited, inserted, or removed.

Usage:  python build_index.py
"""
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / "data"
GENESIS = "GENESIS"


def _sha256_hex(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _chain_hash(prev: str, date: str, manifest_sha: str, bets_sha: str, signature: str) -> str:
    """Deterministic link. Kept simple so index.html can reproduce it byte-for-byte."""
    return _sha256_hex("|".join([prev, date, manifest_sha, bets_sha, signature]).encode())


def build() -> dict:
    days = []
    prev = GENESIS
    for day_dir in sorted(p for p in DATA.iterdir() if p.is_dir()):
        date = day_dir.name
        manifest_path = day_dir / "manifest.json"
        sig_path = day_dir / "bets.sig.json"
        bets_path = day_dir / "bets.json"

        if not manifest_path.exists() or not sig_path.exists():
            raise SystemExit(f"{date}: missing manifest.json or bets.sig.json")

        manifest_sha = _sha256_hex(manifest_path.read_bytes())
        sig = json.loads(sig_path.read_text())

        bets_present = bets_path.exists()
        if bets_present:
            actual = _sha256_hex(bets_path.read_bytes())
            if actual != sig["sha256"]:
                raise SystemExit(
                    f"{date}: bets.json SHA-256 does not match bets.sig.json "
                    f"({actual} != {sig['sha256']}) — file was altered."
                )

        chain = _chain_hash(prev, date, manifest_sha, sig["sha256"], sig["signature"])
        days.append(
            {
                "date": date,
                "timestamp": sig["timestamp"],
                "manifest_sha256": manifest_sha,
                "bets_sha256": sig["sha256"],
                "signature": sig["signature"],
                "bets_present": bets_present,
                "prev": prev,
                "chain": chain,
            }
        )
        prev = chain

    return {
        "generated": datetime.now(timezone.utc).isoformat(),
        "public_key_pem": (ROOT / "keys" / "public_key.pem").read_text().strip(),
        "head": prev,
        "count": len(days),
        "days": days,
    }


def main():
    index = build()
    (ROOT / "index.json").write_text(json.dumps(index, indent=2) + "\n")
    print(f"Wrote index.json — {index['count']} day(s)")
    print(f"HEAD = {index['head']}")
    print("Pin HEAD in the Telegram bio so followers can anchor the whole chain.")


if __name__ == "__main__":
    main()
