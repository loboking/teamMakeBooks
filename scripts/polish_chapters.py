"""챕터 반복 패턴 제거 스크립트.

정규식 기반 후처리 (기본):
  - 행동 묘사 과도한 반복 → 대체 표현으로 로테이션
    (고개를 끄덕였다, 바라보았다, 미세하게, 입을 열었다, 확인했다 등)
    한 챕터에서 2회 초과 시 세 번째부터 대체

LLM 기반 정제 (--llm 플래그):
  - 캐릭터 설명 반복 제거 (등급/직업 묘사)
"""
import argparse
import re
import time
from pathlib import Path

CHAPTERS_DIR = Path("/Volumes/SSD2T/teamMakeBooks/novels/modern_fantasy_game_01/chapters")

# ── 행동 묘사 반복 제거 ──────────────────────────────────────────

# 패턴 → 대체 표현 로테이션
_ACTION_ALTS: list[tuple[re.Pattern, list[str]]] = [
    (re.compile(r'고개를\s*끄덕였다'), [
        '고개를 끄덕였다', '말없이 수긍했다', '끄덕여 보였다',
        '고개를 가볍게 끄덕였다', '표정으로 동의를 보냈다',
        '입가에 미소가 스쳤다', '고개가 살짝 움직였다',
    ]),
    (re.compile(r'고개를\s*돌렸다'), [
        '고개를 돌렸다', '시선을 돌렸다', '고개를 틀었다',
        '방향을 바꿨다', '고개를 돌려보았다',
    ]),
    (re.compile(r'바라보았다'), [
        '바라보았다', '응시했다', '지켜보았다', '눈길을 보냈다',
        '주시했다', '시선을 주었다', '눈으로 좇았다',
        '관찰했다', '시선이 머물렀다', '주목했다',
    ]),
    (re.compile(r'미세하게'), [
        '미세하게', '아주 약간', '희미하게', '가늘게',
        '살짝', '은은하게', '얕게',
    ]),
    (re.compile(r'입을\s*열었다'), [
        '입을 열었다', '말을 꺼냈다', '입을 열어보였다',
        '먼저 말을 걸었다', '침묵을 깼다',
    ]),
    (re.compile(r'확인했다'), [
        '확인했다', '점검했다', '눈으로 살폈다', '다시 한번 살펴보았다',
        '파악했다', '체크했다', '중압했다', '눈여겨보았다',
    ]),
    (re.compile(r'분석했다'), [
        '분석했다', '읽어냈다', '해석했다', '판독했다',
        '추출해냈다', '정보를 정리했다',
    ]),
    (re.compile(r'발동했다'), [
        '발동했다', '가동했다', '작동시켰다', '실행했다', '기동했다',
    ]),
    (re.compile(r'눈을\s*감았다'), [
        '눈을 감았다', '눈을 감아보였다', '천천히 눈을 감았다',
        '눈을 내리깔았다',
    ]),
    (re.compile(r'손을\s*뻗었다'), [
        '손을 뻗었다', '손을 내밀었다', '팔을 뻗었다', '손을 뻗어보였다',
    ]),
    (re.compile(r'깊이\s*숨을'), [
        '깊이 숨을', '길게 숨을', '한숨을', '천천히 숨을',
    ]),
    (re.compile(r'눈을\s*떴다'), [
        '눈을 떴다', '눈을 떠보였다', '눈을 들었다',
    ]),
    (re.compile(r'주먹을\s*쥐었다'), [
        '주먹을 쥐었다', '주먹을 꽉 쥐었다', '손에 힘을 주었다',
        '주먹이 떨렸다',
    ]),
]

_THRESHOLD = 2  # 같은 표현이 2회까지는 허용, 3회째부터 교체


def _dedup_actions(text: str) -> tuple[str, int]:
    """행동 묘사 반복을 대체 표현으로 로테이션. (수정텍스트, 교체수) 반환."""
    total_replaced = 0
    for pattern, alts in _ACTION_ALTS:
        matches = list(pattern.finditer(text))
        if len(matches) <= _THRESHOLD:
            continue

        replace_matches = matches[_THRESHOLD:]
        # 뒤에서부터 치환 (인덱스 변동 방지)
        for idx, m in enumerate(reversed(replace_matches)):
            real_idx = _THRESHOLD + (len(replace_matches) - 1 - idx)
            alt = alts[real_idx % len(alts)]
            text = text[:m.start()] + alt + text[m.end():]
            total_replaced += 1

    return text, total_replaced


def _polish_regex(chapter_path: Path) -> tuple[bool, int]:
    """정규식 기반 반복 제거."""
    text = chapter_path.read_text(encoding='utf-8')

    # 헤더 분리
    lines = text.split('\n')
    header_lines = []
    body_start = 0
    for i, line in enumerate(lines):
        if line.startswith('# ') or line.startswith('> '):
            header_lines.append(line)
            body_start = i + 1
        else:
            break

    body = '\n'.join(lines[body_start:]).strip()
    if not body:
        return False, 0

    body, action_count = _dedup_actions(body)
    if action_count == 0:
        return False, 0

    new_text = '\n'.join(header_lines) + '\n' + body + '\n'
    chapter_path.write_text(new_text, encoding='utf-8')
    return True, action_count


# ── LLM 기반 정제 ──────────────────────────────────────────────────

API_URL = "http://192.168.0.121:11434/api/generate"
MODEL = "gemma4:e2b"
LLM_PROMPT = """다음 소설 본문에서 반복되는 표현을 정제해라.

규칙:
1. "고개를 끄덕였다", "바라보았다", "미세하게", "확인했다" 등 같은 행동 묘사가 3번 이상 반복되면 일부를 다양한 표현으로 교체
2. "이준이 ~했다. 이준이 ~했다." 같이 연속으로 같은 주어가 나오면 대명사(그는/그가)로 치환
3. "F급 짐꾼", "S급 헌터" 같은 캐릭터 설명이 2번 이상 나오면 첫 번째만 남기고 나머지는 삭제 또는 행동 묘사로 교체
4. 대사("...")와 시스템 메시지([...])는 절대 변경 금지
5. 사건·플롯·장면 순서 유지
6. 분량은 원본과 비슷하게 유지
7. 수정 전후 비교나 [원문]/[수정] 같은 마크업 절대 금지
8. 완성된 소설 본문만 그대로 출력. 해설 없이.

본문:
{body}"""


def _polish_llm(chapter_path: Path) -> bool:
    import httpx

    text = chapter_path.read_text(encoding='utf-8')
    lines = text.split('\n')
    header_lines = []
    body_start = 0
    for i, line in enumerate(lines):
        if line.startswith('# ') or line.startswith('> '):
            header_lines.append(line)
            body_start = i + 1
        else:
            break

    body = '\n'.join(lines[body_start:]).strip()
    if not body:
        return False

    chunk_size = 3000
    if len(body) <= chunk_size:
        chunks = [body]
    else:
        paragraphs = body.split('\n\n')
        chunks, current = [], ''
        for p in paragraphs:
            if len(current) + len(p) > chunk_size and current:
                chunks.append(current.strip())
                current = p
            else:
                current = current + '\n\n' + p if current else p
        if current.strip():
            chunks.append(current.strip())

    polished_parts = []
    for i, chunk in enumerate(chunks):
        print(f'  chunk {i+1}/{len(chunks)} ({len(chunk)} chars)...', end=' ', flush=True)
        resp = httpx.post(
            API_URL,
            json={'model': MODEL, 'prompt': LLM_PROMPT.format(body=chunk),
                  'stream': False, 'options': {'temperature': 0.3, 'num_predict': 6000}},
            timeout=600,
        )
        resp.raise_for_status()
        result = resp.json().get('response', '').strip()
        if not result or len(result) < len(chunk) * 0.4:
            print('too short, keep original')
            polished_parts.append(chunk)
        else:
            print(f'ok ({len(result)} chars)')
            polished_parts.append(result)

    polished = '\n\n'.join(polished_parts)
    if len(polished) < len(body) * 0.5:
        print(f'  SKIP: output too short ({len(polished)} vs {len(body)})')
        return False

    new_text = '\n'.join(header_lines) + '\n' + polished + '\n'
    chapter_path.write_text(new_text, encoding='utf-8')
    return True


# ── 메인 ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='챕터 반복 패턴 제거')
    parser.add_argument('start', nargs='?', type=int, default=1)
    parser.add_argument('end', nargs='?', type=int, default=100)
    parser.add_argument('--llm', action='store_true', help='LLM 기반 정제')
    parser.add_argument('--dry-run', action='store_true', help='수정 없이 반복 수만 출력')
    args = parser.parse_args()

    mode = 'LLM' if args.llm else 'regex'
    print(f'모드: {mode} | 대상: ch{args.start:03d}~ch{args.end:03d}')

    total_fixed = 0
    for ch in range(args.start, args.end + 1):
        path = CHAPTERS_DIR / f'ch{ch:03d}.md'
        if not path.exists():
            continue

        if args.llm:
            print(f'ch{ch:03d}: LLM 정제...', end=' ', flush=True)
            t0 = time.time()
            ok = _polish_llm(path)
            elapsed = time.time() - t0
            if ok:
                total_fixed += 1
                print(f'완료 ({elapsed:.0f}s)')
            else:
                print(f'건너뜀 ({elapsed:.0f}s)')
        else:
            if args.dry_run:
                text = path.read_text(encoding='utf-8')
                counts = []
                for pat, alts in _ACTION_ALTS:
                    c = len(pat.findall(text))
                    if c >= _THRESHOLD + 1:
                        short = pat.pattern.split(r'\s')[0].replace(r'\s*', '').replace('\\', '')[:8]
                        counts.append(f'{short}:{c}회')
                print(f'ch{ch:03d}: {", ".join(counts) if counts else "양호"}')
                continue

            ok, n = _polish_regex(path)
            if ok:
                total_fixed += 1
                print(f'ch{ch:03d}: {n}건 교체')
            else:
                print(f'ch{ch:03d}: -')

    print(f'\n총 {total_fixed}화 수정됨')


if __name__ == '__main__':
    main()
