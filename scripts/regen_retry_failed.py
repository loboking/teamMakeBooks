#!/usr/bin/env python3
"""실패한 회차만 개별 재시도. regen_full.py --from/--to를 회차별로 반복."""
import subprocess
import sys

FAILED = [1,4,5,6,7,9,10]

if __name__ == "__main__":
    for n in FAILED:
        print(f"\n{'='*40} ch{n:03d} {'='*40}", flush=True)
        r = subprocess.run([
            sys.executable, "scripts/regen_full.py",
            "--work-id", "isekai_slowlife_trade_01",
            "--from", str(n), "--to", str(n),
            "--skip-body-delete",
        ])
        if r.returncode != 0:
            print(f"  ch{n:03d} 스크립트 오류 (rc={r.returncode})", flush=True)
