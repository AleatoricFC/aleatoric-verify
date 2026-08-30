# AleatoricFC — Proof of Bets

Every bet is cryptographically **locked before kick-off** and published here. This
repo is the permanent, tamper-evident record behind the [@AleatoricFC](https://t.me/AleatoricFC)
Telegram channel.

## ✅ Verify in one tap (no install)

**→ https://aleatoricfc.github.io/aleatoric-verify/**

Open the page. It checks every signature **live, in your browser** — nothing to
download, works on a phone. A green banner means every bet was signed before the
matches started and nothing has been changed since.

## How the guarantee works

Each day has a folder under [`data/`](data/):

| file | published | contains |
|------|-----------|----------|
| `manifest.json` | on bet day | the fixtures + markets being bet — **no** outcome, price or stake |
| `bets.sig.json` | on bet day | an Ed25519 signature that locks the *full* bets before any match starts |
| `bets.json` | the next day | the full bets: outcome, price, stake, model probabilities |

Because the signature only matches the exact bets that were locked in, they can't be
edited, cherry-picked, or backdated once results are known. The next-day reveal proves
the hidden bets were the ones committed to.

### The chain

Every day links to the previous one via a `prev` hash in [`index.json`](index.json).
A single **head** hash covers the entire history — change, add, or remove any past day
and the head changes. The current head is **pinned in the Telegram channel bio**:

```
HEAD  b9fce3ef31bab06d0d205778294773620e7899bf0cb6e3ce63b0fd6c233e71d9
```

## Verify from the command line (for auditors)

Trust nothing but the pinned public key:

```bash
git clone https://github.com/AleatoricFC/aleatoric-verify
cd REPO
pip install cryptography
python verify.py            # all days + the chain head
python verify.py 2026-08-30 # one day
```

The public key is in [`keys/public_key.pem`](keys/public_key.pem) and also pinned in
the Telegram channel — compare the two.

## Maintainer notes

```bash
python add_day.py commit --date YYYY-MM-DD --push   # bet day: manifest + signature
python add_day.py reveal --date YYYY-MM-DD --push   # next day: full bets
```

`add_day.py` copies the signed files out of `betting_service`, rebuilds the hash chain,
and pushes. After each run, update the pinned HEAD in the Telegram bio.
