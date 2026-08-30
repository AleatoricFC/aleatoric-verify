#!/usr/bin/env python3
"""
Publish a day to the public record, mirroring the Telegram timing so the repo
keeps the same "committed before kick-off" guarantee.

Two phases per day:

    # on bet day — publish the redacted manifest + the signature (NOT the bets)
    python add_day.py commit --date 2026-08-31

    # the following day — reveal the full bets
    python add_day.py reveal --date 2026-08-31

Both phases rebuild index.json (the hash chain) and, with --push, commit and push.
Source files are read from the betting_service working dir by default.

    bet_manifest_YYYYMMDD.json  ->  data/YYYY-MM-DD/manifest.json
    bets_YYYYMMDD.sig.json      ->  data/YYYY-MM-DD/bets.sig.json
    bets_YYYYMMDD.json          ->  data/YYYY-MM-DD/bets.json   (reveal only)
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import build_index

ROOT = Path(__file__).parent
DEFAULT_SRC = Path("/home/eyuel/betting_service")


def _copy(src: Path, dst: Path):
    if not src.exists():
        sys.exit(f"missing source file: {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"  {src.name}  ->  {dst.relative_to(ROOT)}")


def _git(*args):
    subprocess.run(["git", "-C", str(ROOT), *args], check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=["commit", "reveal"])
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--from", dest="src", default=str(DEFAULT_SRC), help="source dir")
    ap.add_argument("--push", action="store_true", help="git commit + push after")
    args = ap.parse_args()

    src = Path(args.src)
    iso = args.date
    compact = iso.replace("-", "")
    day = ROOT / "data" / iso

    if args.phase == "commit":
        _copy(src / f"bet_manifest_{compact}.json", day / "manifest.json")
        _copy(src / f"bets_{compact}.sig.json", day / "bets.sig.json")
        msg = f"commit {iso}: manifest + signature (bets locked, revealed tomorrow)"
    else:
        if not (day / "bets.sig.json").exists():
            sys.exit(f"{iso} was never committed — run `commit` first")
        _copy(src / f"bets_{compact}.json", day / "bets.json")
        msg = f"reveal {iso}: full bets"

    index = build_index.build()
    (ROOT / "index.json").write_text(
        __import__("json").dumps(index, indent=2) + "\n"
    )
    print(f"index.json rebuilt — {index['count']} days, HEAD {index['head'][:16]}…")

    if args.push:
        _git("add", "-A")
        dirty = subprocess.run(
            ["git", "-C", str(ROOT), "status", "--porcelain"],
            capture_output=True, text=True,
        ).stdout.strip()
        if dirty:
            _git("commit", "-m", msg)
            _git("push")
            print("pushed.")
        else:
            print("no changes — nothing to push.")
    else:
        print("run with --push to commit and push.")
    print(f"\nHEAD to pin in Telegram bio:\n  {index['head']}")


if __name__ == "__main__":
    main()
