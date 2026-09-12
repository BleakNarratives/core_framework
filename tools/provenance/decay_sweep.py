#!/usr/bin/env python3
# decay_sweep — deletes expired CAPS ghost wormholes after 14d of decay
import pathlib, json, re, sys
from datetime import datetime, timezone, timedelta
HOME = pathlib.Path.home()
LEDGER = HOME / "pheromones.jsonl"
def _is_expired_ghost(path: pathlib.Path, cutoff_days=14) -> bool:
    if not path.exists(): return False
    txt = path.read_text(errors="replace")
    if "[HOP WORMHOLE" not in txt or "```caps-stego" not in txt: return False
    m = re.search(r"decays (\d{4}-\d{2}-\d{2})", txt)
    if not m: return False
    try:
        d = datetime.strptime(m.group(1), "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) > d + timedelta(days=1)  # +1 day grace
    except: return False

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--delete", action="store_true")
    args = ap.parse_args()
    expired = []
    for p in HOME.iterdir():
        if not p.is_file(): continue
        if _is_expired_ghost(p):
            expired.append(p)
    for q in [HOME/"puter_models.json"]:
        # json stub ghost check: _decays field
        if q.exists():
            try:
                j=json.loads(q.read_text())
                if j.get("_decays") and j.get("_hop")=="MOVED":
                    from datetime import datetime as dt
                    d=dt.strptime(j["_decays"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    if datetime.now(timezone.utc) > d + timedelta(days=1):
                        expired.append(q)
            except: pass
    if args.check or not args.delete:
        print(f"expired ghosts: {len(expired)}")
        for p in expired: print(f"  {p.name}")
    if args.delete and expired:
        for p in expired:
            print(f"deleting {p}")
            # p.unlink()  # disabled — require resonance check
            print("  (delete disabled — run resonance check first: python3 ~/RootBase/resonance.py check \"rm <file>\")")
