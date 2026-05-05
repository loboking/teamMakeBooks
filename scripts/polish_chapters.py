"""챕터 1~10 반복 캐릭터 소개 제거 스크립트."""
import json
import re
import sys
import time
from pathlib import Path

import httpx

CHAPTERS_DIR = Path("/Volumes/SSD2T/teamMakeBooks/novels/modern_fantasy_game_01/chapters")
API_URL = "http://192.168.0.121:11434/api/generate"
MODEL = "gemma4:e2b"
MODEL = "gemma4:e2b"
PROMPT = """다음 소설 본문에서 캐릭터 설명이 반복되는 부분을 정제해라.

규칙:
1. "F급 짐꾼", "B급 어쌔신", "5년간 짐꾼", "S급 헌터" 같은 설명이 2번 이상 나오면 첫 번째만 남기고 나머지는 삭제 또는 행동 묘사로 교체
2. 대사("...")와 시스템 메시지([...])는 절대 변경 금지
3. 사건·플롯·장면 순서 유지
4. 분량은 원본과 비슷하게 유지
5. 수정 전후 비교나 [원문]/[수정] 같은 마크업 절대 금지
6. 완성된 소설 본문만 그대로 출력. 해설 없이.

본문:
{body}"""

def polish_chunk(body: str) -> str:
    """한 청크를 LLM으로 정제."""
    prompt = PROMPT.format(body=body)
    resp = httpx.post(
        API_URL,
        json={"model": MODEL, "prompt": prompt, "stream": False,
              "options": {"temperature": 0.3, "num_predict": 6000}},
        timeout=600,
    )
    resp.raise_for_status()
    return resp.json().get("response", "").strip()


def polish_chapter(chapter_path: Path) -> bool:
    text = chapter_path.read_text(encoding="utf-8")

    # 제목줄과 AI 배지 분리
    lines = text.split("\n")
    header_lines = []
    body_start = 0
    for i, line in enumerate(lines):
        if line.startswith("# ") or line.startswith("> "):
            header_lines.append(line)
            body_start = i + 1
        else:
            break

    body = "\n".join(lines[body_start:]).strip()
    if not body:
        return False

    # 3000자 단위로 분할 처리
    chunk_size = 3000
    if len(body) <= chunk_size:
        chunks = [body]
    else:
        # 문단 단위로 분할
        paragraphs = body.split("\n\n")
        chunks = []
        current = ""
        for p in paragraphs:
            if len(current) + len(p) > chunk_size and current:
                chunks.append(current.strip())
                current = p
            else:
                current = current + "\n\n" + p if current else p
        if current.strip():
            chunks.append(current.strip())

    polished_parts = []
    try:
        for i, chunk in enumerate(chunks):
            print(f"  chunk {i+1}/{len(chunks)} ({len(chunk)} chars)...", end=" ", flush=True)
            result = polish_chunk(chunk)
            if not result or len(result) < len(chunk) * 0.4:
                print(f"too short, keep original")
                polished_parts.append(chunk)
            else:
                print(f"ok ({len(result)} chars)")
                polished_parts.append(result)
    except Exception as e:
        print(f"  ERROR: {e}")
        return False

    polished = "\n\n".join(polished_parts)
    if len(polished) < len(body) * 0.5:
        print(f"  SKIP: total output too short ({len(polished)} vs {len(body)})")
        return False

    # 재조합
    new_text = "\n".join(header_lines) + "\n" + polished + "\n"
    chapter_path.write_text(new_text, encoding="utf-8")
    return True


def main():
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    end = int(sys.argv[2]) if len(sys.argv) > 2 else 10

    for ch in range(start, end + 1):
        path = CHAPTERS_DIR / f"ch{ch:03d}.md"
        if not path.exists():
            print(f"ch{ch:03d}: 파일 없음, 건너뜀")
            continue

        orig_size = path.stat().st_size
        print(f"ch{ch:03d}: 정제 시작 ({orig_size} bytes)...", end=" ", flush=True)

        t0 = time.time()
        ok = polish_chapter(path)
        elapsed = time.time() - t0

        new_size = path.stat().st_size
        if ok:
            print(f"완료 ({elapsed:.0f}s, {orig_size}→{new_size} bytes, {'+'if new_size>orig_size else ''}{new_size-orig_size})")
        else:
            print(f"실패 ({elapsed:.0f}s)")


if __name__ == "__main__":
    main()
