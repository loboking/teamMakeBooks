#!/usr/bin/env python3
"""실패 케이스 분석 리포트."""
from __future__ import annotations
import argparse, json, re, sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILURES_DIR = ROOT / "logs" / "failures"


def load_records(since_days):
    if not FAILURES_DIR.exists():
        return []
    cutoff = None
    if since_days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
    records = []
    for fp in sorted(FAILURES_DIR.glob("*.json")):
        try:
            r = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        if cutoff:
            try:
                ts = datetime.fromisoformat(r.get("failed_at", "").replace("Z", "+00:00"))
                if ts < cutoff: continue
            except Exception: pass
        records.append(r)
    return records


def top_keywords(reasons, top_n=10):
    bag = Counter()
    skip = {"이상","이하","있다","없다","이는","그것","이것","있음","없음"}
    for r in reasons:
        for w in re.findall(r"[가-힣]{2,}", r):
            if w in skip: continue
            bag[w] += 1
    return bag.most_common(top_n)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--since", type=int, default=30)
    p.add_argument("--chapter", type=int)
    p.add_argument("--stage")
    args = p.parse_args()

    records = load_records(args.since)
    if args.chapter is not None:
        records = [r for r in records if r.get("chapter_n") == args.chapter]
    if args.stage:
        records = [r for r in records if r.get("failure_stage") == args.stage]

    print(f"\n📊 실패 리포트 — 최근 {args.since}일")
    print(f"총 실패 건수: {len(records)}\n")
    if not records:
        print("(실패 기록 없음)")
        return 0

    stage_count = Counter(r["failure_stage"] for r in records)
    print("【단계별 실패】")
    for s, n in stage_count.most_common(): print(f"  {s:<12} {n}건")
    print()

    chapter_count = Counter(r["chapter_n"] for r in records)
    print("【회차별 실패 (Top 10)】")
    for ch, n in chapter_count.most_common(10): print(f"  ch{ch:03d}  {n}건")
    print()

    reasons = [r.get("failure_reason","") for r in records if r.get("failure_reason")]
    if reasons:
        print("【사유 키워드 빈도】")
        for w, n in top_keywords(reasons, 12): print(f"  {w:<10} {n}건")
        print()

    repeat = [(ch, n) for ch, n in chapter_count.items() if n >= 3]
    if repeat:
        print("【⚠️ 반복 실패 회차 (≥3회) — 룰 조정 신호】")
        for ch, n in sorted(repeat, key=lambda x: -x[1]):
            stages = Counter(r["failure_stage"] for r in records if r["chapter_n"] == ch)
            print(f"  ch{ch:03d}  {n}건  단계분포: {dict(stages)}")
        print()

    print("【최근 실패 5건】")
    for r in sorted(records, key=lambda x: x.get("failed_at",""), reverse=True)[:5]:
        ch = r["chapter_n"]; stage = r["failure_stage"]
        when = r.get("failed_at","?")[:19]
        reason = r.get("failure_reason","")[:120]
        print(f"  [{when}] ch{ch:03d} / {stage}")
        print(f"    사유: {reason}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
