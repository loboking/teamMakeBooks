#!/usr/bin/env python3
"""작품 본문 전체 재생성 — outline 없는 화는 자동 생성, 본문은 일괄.

Usage:
  python scripts/regen_full.py --work-id <wid> --from 1 --to 225
"""
from __future__ import annotations

import argparse
import json
import re
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


def ensure_outline(
    n: int, work_id: str, settings, concept, ending, outlines_dir: Path,
    writer: MetaWriterAgent, acts: list,
) -> bool:
    """ch_n.yaml 없으면 생성. 있으면 True."""
    yaml_path = outlines_dir / f"ch{n:03d}.yaml"
    if yaml_path.exists():
        return True

    # 해당 화의 act_idx
    act_idx = 0
    for i, a in enumerate(acts):
        r = a.get("range", [0, 0])
        if int(r[0]) <= n <= int(r[1]):
            act_idx = i
            break

    # 직전 2화 컨텍스트 (outline 또는 기존 본문 요약)
    prev_chapters: list[dict] = []
    for p_n in [n - 2, n - 1]:
        if p_n < 1:
            continue
        p_yaml = outlines_dir / f"ch{p_n:03d}.yaml"
        if p_yaml.exists():
            try:
                d = yaml.safe_load(p_yaml.read_text(encoding="utf-8"))
                prev_chapters.append({"chapter_n": p_n, "overall": d.get("overall", "")})
            except Exception:
                pass

    # 1단계: overall 생성 — 단순 프롬프트 우선, 실패 시 전체 프롬프트 폴백
    overall = ""

    # 직전 회차 컨텍스트 요약
    prev_ctx = ""
    if prev_chapters:
        for p in prev_chapters[-2:]:
            prev_ctx += f"ch{int(p.get('chapter_n',0)):03d}: {str(p.get('overall',''))[:150]}\n"

    # 막 정보
    act_name = acts[act_idx].get("name", f"{act_idx+1}막") if act_idx < len(acts) else ""
    protagonist = concept.get("protagonist", "차하린")

    simple_prompt = (
        f"한국 이세계물 웹소설 {act_name} ch{n:03d}회차 줄거리.\n"
        f"주인공: {protagonist}\n"
        f"장르: {concept.get('genre', '이세계물')}\n"
        f"분위기: {concept.get('mood', '')}\n\n"
    )
    if prev_ctx:
        simple_prompt += f"[직전 회차]\n{prev_ctx}\n"
    simple_prompt += (
        f"ch{n:03d} 줄거리를 200~300자 한국어로 작성.\n"
        f"핵심 사건 1~2개, 감정 변화, 다음 회 후크 포함.\n"
        f"인물 소개 반복 금지. 줄거리 본문만 출력."
    )

    full_prompt = build_plot_chapter_prompt(
        concept, ending, act_idx=act_idx, chapter_n=n,
        prev_chapters=prev_chapters, work_id=work_id,
    )
    full_prompt += "\n\n출력 형식: 200~300자 한국어 한 단락. JSON·마크다운 헤딩 금지. 줄거리 본문만 작성."

    # 단순 프롬프트 먼저 시도, 실패 시 전체 프롬프트
    for attempt, prompt in enumerate([simple_prompt, full_prompt]):
        for retry in range(3):
            try:
                resp = writer.provider.complete(
                    prompt, max_tokens=500,
                    temperature=0.7 + retry * 0.1,
                )
                log_call(team="meta_writer", role=f"regen_overall_ch{n:03d}_a{attempt}_t{retry+1}",
                         work_id=work_id, chapter_n=n, prompt=prompt, response=resp,
                         logs_dir=settings.logs_dir)
                txt = resp.text.strip()
                txt = re.sub(r'^```.*$', '', txt, flags=re.MULTILINE).strip()
                txt = re.sub(r'^#+\s.*$', '', txt, flags=re.MULTILINE).strip()
                m = re.search(r'"overall"\s*:\s*"((?:[^"\\]|\\.)*)"', txt)
                if m:
                    try:
                        overall = json.loads(f'"{m.group(1)}"').strip()
                    except Exception:
                        overall = m.group(1).strip()
                else:
                    overall = txt.strip()
                if len(overall) >= 60:
                    break
            except LLMProviderError as e:
                print(f"  ch{n:03d} overall 실패 (a{attempt} t{retry+1}): {e}", flush=True)
        if len(overall) >= 60:
            break

    if len(overall) < 60:
        print(f"  ch{n:03d} outline skip — overall 짧음 ({len(overall)}자)", flush=True)
        return False

    # 2단계: beats 확장
    try:
        chapter = {"chapter_n": n, "act": act_idx + 1, "overall": overall}
        expanded = writer.expand_chapter_to_beats(concept, ending, chapter, work_id=work_id)
        yaml_data = {
            "chapter_n": expanded["chapter_n"],
            "overall": expanded["overall"],
            "beats": expanded["beats"],
        }
        yaml_path.write_text(
            yaml.safe_dump(yaml_data, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        print(f"  ch{n:03d} outline 생성", flush=True)
        return True
    except LLMProviderError as e:
        print(f"  ch{n:03d} outline 실패: {e}", flush=True)
        return False


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--work-id", required=True)
    p.add_argument("--from", dest="ch_from", type=int, required=True)
    p.add_argument("--to", dest="ch_to", type=int, required=True)
    p.add_argument("--skip-body-delete", action="store_true",
                   help="기존 본문 삭제 안 함 (있으면 skip)")
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
    acts = ending.get("acts", [])

    cfg = settings.config.get("meta_writer", {})
    writer = MetaWriterAgent(
        get_provider(settings.model_key("meta_writer", "plot_skeleton"), settings),
        temperature=float(cfg.get("plot_skeleton_temperature", 0.7)),
        num_predict=int(cfg.get("plot_skeleton_num_predict", 2000)),
        logs_dir=settings.logs_dir,
    )

    # 기존 본문 삭제 (re-generate)
    if not args.skip_body_delete:
        for n in range(args.ch_from, args.ch_to + 1):
            for suffix in (".md", "_meta.json", "_summary.md"):
                p = chapters_dir / f"ch{n:03d}{suffix}"
                if p.exists():
                    p.unlink()
        print(f"[regen] 기존 본문 ch{args.ch_from}~ch{args.ch_to} 삭제 완료")

    # 각 화: outline 확보 + 본문 생성
    for n in range(args.ch_from, args.ch_to + 1):
        # outline 확보
        if not ensure_outline(n, args.work_id, settings, concept, ending,
                              outlines_dir, writer, acts):
            print(f"=== ch{n:03d} skip (outline 없음) ===", flush=True)
            continue

        # 본문
        print(f"=== ch{n:03d} 본문 ===", flush=True)
        try:
            t0 = time.time()
            result = run_chapter_pipeline(work_id=args.work_id, chapter_n=n, settings=settings)
            status = "OK" if result.success else f"FAIL({result.failure_stage})"
            print(f"  ch{n:03d} {status} ({time.time()-t0:.1f}s)", flush=True)
        except Exception as e:
            print(f"  ch{n:03d} 예외: {e}", flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
