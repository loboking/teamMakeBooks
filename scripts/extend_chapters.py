#!/usr/bin/env python3
"""기존 작품의 plot_skeleton 일부 + outlines + 본문을 추가 생성.

quick_init이 만든 작품에 대해 ch_from ~ ch_to 범위 회차의 줄거리/아웃라인/본문을 한 번에.

Usage:
  python scripts/extend_chapters.py --work-id <wid> --from 3 --to 20
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.config import load_settings  # noqa: E402
from app.orchestrator import run_chapter_pipeline  # noqa: E402
from app.providers import LLMProviderError, get_provider  # noqa: E402
from app.teams.meta_writer import MetaWriterAgent  # noqa: E402
from app.teams.meta_writer.prompts import (  # noqa: E402
    PLOT_CHAPTER_SCHEMA,
    build_plot_chapter_prompt,
)
from app.utils.logger import log_call  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--work-id", required=True)
    p.add_argument("--from", dest="ch_from", type=int, required=True)
    p.add_argument("--to", dest="ch_to", type=int, required=True)
    p.add_argument("--skip-bodies", action="store_true")
    args = p.parse_args()

    settings = load_settings(ROOT)
    work_dir = settings.novels_dir / args.work_id
    init_dir = work_dir / "_init"
    outlines_dir = work_dir / "chapter_outlines"
    chapters_dir = work_dir / "chapters"
    outlines_dir.mkdir(parents=True, exist_ok=True)
    chapters_dir.mkdir(parents=True, exist_ok=True)

    concept = yaml.safe_load((init_dir / "concept.yaml").read_text(encoding="utf-8"))
    ending = yaml.safe_load((init_dir / "ending.yaml").read_text(encoding="utf-8"))

    # 마일스톤·기존 ch001/002 등 사용 가능한 화를 컨텍스트로
    existing: list[dict] = []
    for n in sorted([1, 2, 50, 100, 150, 200, 225]):
        f = outlines_dir / f"ch{n:03d}.yaml"
        if f.exists():
            d = yaml.safe_load(f.read_text(encoding="utf-8"))
            existing.append({"chapter_n": n, "overall": d.get("overall", "")})

    cfg = settings.config.get("meta_writer", {})
    writer = MetaWriterAgent(
        get_provider(settings.model_key("meta_writer", "plot_skeleton"), settings),
        temperature=float(cfg.get("plot_skeleton_temperature", 0.7)),
        num_predict=int(cfg.get("plot_skeleton_num_predict", 2000)),
        logs_dir=settings.logs_dir,
    )

    # 화별 act_idx 자동 매칭 (range에 따라)
    acts = ending.get("acts", [])
    def _act_idx_for(n: int) -> int:
        for i, a in enumerate(acts):
            r = a.get("range", [0, 0])
            if int(r[0]) <= n <= int(r[1]):
                return i
        return 0  # 폴백
    # 시작 화의 act_idx 사용 (한 막 안에 들어오는 범위만 진행 권장)
    act_idx = _act_idx_for(args.ch_from)
    rng = acts[act_idx].get("range", [1, 75])
    print(f"[extend] 시작 화 ch{args.ch_from} → act{act_idx+1} {rng}")

    # ─ 1. ch_from ~ ch_to overall 생성 — build_plot_chapter_prompt 단일 화 직접 호출
    new_overalls: list[dict] = []
    prev_ctx = existing[:]
    import re as _re
    import json as _json
    for n in range(args.ch_from, args.ch_to + 1):
        # 직전 2화 컨텍스트
        prev_for_n = sorted([c for c in prev_ctx if c["chapter_n"] < n], key=lambda c: c["chapter_n"])[-2:]
        prompt = build_plot_chapter_prompt(
            concept, ending,
            act_idx=act_idx, chapter_n=n,
            prev_chapters=prev_for_n, work_id=args.work_id,
        )
        overall = ""
        # gemma2:9b는 format_schema 호환성 떨어짐 — 일반 텍스트 응답에서 overall 추출
        plain_prompt = (
            prompt + "\n\n출력 형식: 200~300자 한국어 한 단락. JSON·마크다운 헤딩 금지. "
            "현재 회차 줄거리 본문만 작성."
        )
        for retry in range(2):
            try:
                resp = writer.provider.complete(
                    plain_prompt,
                    max_tokens=600,
                    temperature=0.7,
                )
                log_call(team="meta_writer", role=f"extend_ch{n:03d}_t{retry+1}",
                         work_id=args.work_id, chapter_n=n, prompt=plain_prompt, response=resp,
                         logs_dir=settings.logs_dir)
                txt = resp.text.strip()
                # JSON 마크 제거 + 마크다운 헤딩·코드블록 제거
                txt = _re.sub(r'^```.*$', '', txt, flags=_re.MULTILINE).strip()
                txt = _re.sub(r'^#+\s.*$', '', txt, flags=_re.MULTILINE).strip()
                m = _re.search(r'"overall"\s*:\s*"((?:[^"\\]|\\.)*)"', txt)
                if m:
                    try:
                        overall = _json.loads(f'"{m.group(1)}"').strip()
                    except Exception:
                        overall = m.group(1).strip()
                else:
                    overall = txt.strip()
                if len(overall) >= 100:
                    break
            except LLMProviderError as e:
                print(f"  ch{n:03d} LLM 실패: {e}", flush=True)

        if len(overall) < 100:
            print(f"  ch{n:03d} overall 실패 (len={len(overall)})")
            continue

        ch = {"chapter_n": n, "act": act_idx + 1, "overall": overall}
        new_overalls.append(ch)
        prev_ctx.append({"chapter_n": n, "overall": overall})
        print(f"  ch{n:03d} overall OK ({len(overall)}자)")

    # ─ 2. outline (beats 2개) 생성
    print(f"\n[extend] outline 변환 시작...")
    for ch in new_overalls:
        n = ch["chapter_n"]
        try:
            t0 = time.time()
            expanded = writer.expand_chapter_to_beats(concept, ending, ch, work_id=args.work_id)
            out_data = {
                "chapter_n": expanded["chapter_n"],
                "overall": expanded["overall"],
                "beats": expanded["beats"],
            }
            (outlines_dir / f"ch{n:03d}.yaml").write_text(
                yaml.safe_dump(out_data, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
            print(f"  ch{n:03d} outline ({time.time()-t0:.1f}s)")
        except LLMProviderError as e:
            print(f"  ch{n:03d} outline 실패: {e}")

    # ─ 3. 본문 생성
    if args.skip_bodies:
        print("[extend] --skip-bodies 지정 — 본문 생성 생략")
        return 0

    print(f"\n[extend] 본문 생성 시작...")
    for n in range(args.ch_from, args.ch_to + 1):
        if not (outlines_dir / f"ch{n:03d}.yaml").exists():
            print(f"  ch{n:03d} skip (outline 없음)")
            continue
        try:
            print(f"=== ch{n:03d} 본문 ===")
            t0 = time.time()
            result = run_chapter_pipeline(work_id=args.work_id, chapter_n=n, settings=settings)
            status = "OK" if result.success else f"FAIL({result.failure_stage})"
            print(f"  ch{n:03d} {status} ({time.time()-t0:.1f}s)")
        except Exception as e:
            print(f"  ch{n:03d} 예외: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
