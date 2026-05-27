"""GLM-5-turbo 기반 '이준' 반복 감소 dry-run 테스트."""
import httpx
import json
import re
import sys
import time
from pathlib import Path

API_URL = "https://api.z.ai/api/paas/v4/chat/completions"
API_KEY = "5c6866f0af89426aa72f74e10e8900c9.6ItYPCL55z0wCExr"
MODEL = "glm-5-turbo"

CHAPTERS_DIR = Path("/Volumes/SSD2T/teamMakeBooks/novels/modern_fantasy_game_01/chapters")
OUTPUT_DIR = CHAPTERS_DIR / "backup_before_polish"

PROMPT = """다음 소설 본문에서 "이준"이라는 이름이 과도하게 반복되는 부분을 정제해라.

규칙:
1. 한 줄/단락 내에서 "이준"이 3번 이상 나오면, 문맥에 맞게 대명사(그는, 그가, 그의, 그를)로 치환하거나 주어 생략
2. 앞뒤 문맥에서 주어가 명확하면 "이준"을 생략해도 됨
3. 대화에서 상대방을 지칭하는 "이준"은 그대로 유지 (예: "이준 씨", "이준아")
4. 시스템 메시지([...]) 안의 내용은 변경 금지
5. 사건·플롯·장면 순서 절대 유지
6. 분량은 원본과 ±5% 이내로 유지
7. 수정 전후 비교나 [원문]/[수정] 같은 마크업 절대 금지
8. 완성된 소설 본문만 그대로 출력. 해설 없이.

본문:
{body}"""


def count_ijun(text: str) -> int:
    return len(re.findall(r'이준', text))


def process_chapter(ch_num: int):
    path = CHAPTERS_DIR / f'ch{ch_num:03d}.md'
    if not path.exists():
        print(f'ch{ch_num:03d}: 파일 없음')
        return

    text = path.read_text(encoding='utf-8')

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
    original_count = count_ijun(body)
    original_len = len(body)

    print(f'ch{ch_num:03d}: "이준" {original_count}회, 본문 {original_len}자')

    # API 호출
    print('  GLM-5-turbo 호출 중...', end=' ', flush=True)
    t0 = time.time()

    resp = httpx.post(
        API_URL,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            'model': MODEL,
            'messages': [
                {'role': 'user', 'content': PROMPT.format(body=body)},
            ],
            'temperature': 0.3,
            'max_tokens': 8000,
        },
        timeout=120,
    )

    elapsed = time.time() - t0

    if resp.status_code != 200:
        print(f'API 에러 {resp.status_code}: {resp.text[:200]}')
        return

    data = resp.json()
    result = data['choices'][0]['message']['content'].strip()

    new_count = count_ijun(result)
    new_len = len(result)
    reduction = original_count - new_count
    reduction_pct = (reduction / original_count * 100) if original_count else 0
    len_diff_pct = ((new_len - original_len) / original_len * 100) if original_len else 0

    print(f'{elapsed:.0f}s')
    print(f'  결과: "이준" {new_count}회 ({reduction}회 감소, {reduction_pct:.0f}%)')
    print(f'  분량: {new_len}자 ({len_diff_pct:+.1f}%)')

    # dry-run 결과 저장
    if not OUTPUT_DIR.exists():
        OUTPUT_DIR.mkdir(parents=True)

    out_path = OUTPUT_DIR / f'ch{ch_num:03d}_glm_test.md'
    new_text = '\n'.join(header_lines) + '\n' + result + '\n'
    out_path.write_text(new_text, encoding='utf-8')
    print(f'  저장: {out_path}')


if __name__ == '__main__':
    ch = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    process_chapter(ch)
