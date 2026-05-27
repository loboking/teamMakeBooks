"""문맥 보존 '이준' 반복 감소 v4 — 단락 내 + 교차 줄 컨텍스트.

1. 같은 줄에서 2회 이상 → 2회째부터 대명사
2. 이전 서술줄에서 이준이 주어였으면 → 다음 서술줄의 첫 이준도 대명사
3. 대사/시스템 메시지는 절대 변경하지 않음
"""
import re
from pathlib import Path

CHAPTERS_DIR = Path("/Volumes/SSD2T/teamMakeBooks/novels/modern_fantasy_game_01/chapters")

_PRONOUN_MAP = {
    '이준은': '그는',
    '이준이': '그가',
    '이준을': '그를',
    '이준의': '그의',
}
_IJUN_PAT = re.compile(r'이준([은는이가을를의])')
_IJUN_FULL = re.compile(r'이준')


def _is_protected(line: str) -> bool:
    s = line.strip()
    if not s or s.startswith('#') or s.startswith('[') or s.startswith('>'):
        return True
    if s.startswith('"'):
        return True
    if ':' in s[:15]:
        return True
    if s.startswith('---'):
        return True
    return False


def _count_ijun(text: str) -> int:
    return len(_IJUN_FULL.findall(text))


def _line_starts_with_ijun_subject(line: str) -> bool:
    """줄 시작 부분(15자 내)에 이준+주어 조사가 있는지."""
    s = line.lstrip()
    return bool(re.match(r'이준[은는이가]', s))


def _replace_first_ijun(line: str) -> tuple[str, bool]:
    """줄의 첫 이준을 대명사로 치환. 성공시 (새줄, True)."""
    m = _IJUN_PAT.search(line)
    if not m:
        return line, False
    # 호칭 체크
    after = line[m.end():m.end()+2]
    if after and after[0] in '씨아!':
        return line, False
    # 앞에 다른 한글 문자가 있으면 스킵
    before = line[max(0,m.start()-1):m.start()]
    if before and re.search(r'[가-힣]$', before):
        return line, False

    particle = m.group(1) or ''
    key = '이준' + particle
    pronoun = _PRONOUN_MAP.get(key, '그')
    return line[:m.start()] + pronoun + line[m.end():], True


def dedup_v4(text: str) -> tuple[str, int]:
    lines = text.split('\n')
    new_lines = []
    total = 0
    prev_had_ijun_subject = False

    for line in lines:
        if not line.strip():
            new_lines.append(line)
            prev_had_ijun_subject = False
            continue

        if _is_protected(line):
            new_lines.append(line)
            prev_had_ijun_subject = False
            continue

        matches = list(_IJUN_PAT.finditer(line))
        if not matches:
            new_lines.append(line)
            prev_had_ijun_subject = False
            continue

        new_line = line

        # 1) 같은 줄에서 2회 이상 → 2회째부터 대명사 (뒤에서부터)
        if len(matches) >= 2:
            for idx in range(len(matches) - 1, 0, -1):
                m = matches[idx]
                after = new_line[m.end():m.end()+2]
                if after and after[0] in '씨아!':
                    continue
                before = new_line[max(0,m.start()-1):m.start()]
                if before and re.search(r'[가-힣]$', before):
                    continue
                particle = m.group(1) or ''
                key = '이준' + particle
                pronoun = _PRONOUN_MAP.get(key, '그')
                new_line = new_line[:m.start()] + pronoun + new_line[m.end():]
                total += 1
            # 매치 재계산
            matches = list(_IJUN_PAT.finditer(new_line))

        # 2) 교차 줄: 이전 줄에서 이준 주어였고, 이 줄 시작이 이준 주어이면 대명사
        if prev_had_ijun_subject and matches:
            first_m = matches[0]
            s = new_line.lstrip()
            offset = len(new_line) - len(s)
            if first_m.start() < offset + 15:
                after = new_line[first_m.end():first_m.end()+2]
                before = new_line[max(0,first_m.start()-1):first_m.start()]
                if not (after and after[0] in '씨아!') and not (before and re.search(r'[가-힣]$', before)):
                    particle = first_m.group(1) or ''
                    key = '이준' + particle
                    pronoun = _PRONOUN_MAP.get(key, '그')
                    new_line = new_line[:first_m.start()] + pronoun + new_line[first_m.end():]
                    total += 1

        new_lines.append(new_line)

        # 다음 줄 컨텍스트: 이 줄에서 마지막 이준이 주어 역할이었는지
        final_matches = list(_IJUN_PAT.finditer(new_line))
        if final_matches:
            last = final_matches[-1]
            # 주어 조사인지
            is_subject = last.group(1) in ('은', '이')
            # 문장 끝 부분에 있는지 (주로 문장 끝에 주어가 오면 다음 줄의 주어를 암시)
            after_last = new_line[last.end():].strip()
            is_near_end = len(after_last) < 20
            prev_had_ijun_subject = is_subject and is_near_end
        else:
            prev_had_ijun_subject = False

    return '\n'.join(new_lines), total


def dry_run(ch_num: int, show_diff: bool = True):
    path = CHAPTERS_DIR / f'ch{ch_num:03d}.md'
    if not path.exists():
        print(f'ch{ch_num:03d}: 파일 없음')
        return

    text = path.read_text(encoding='utf-8')
    orig_count = _count_ijun(text)
    orig_len = len(text)

    new_text, replaced = dedup_v4(text)
    new_count = _count_ijun(new_text)
    new_len = len(new_text)

    reduction = orig_count - new_count
    pct = (reduction / orig_count * 100) if orig_count else 0
    len_pct = ((new_len - orig_len) / orig_len * 100) if orig_len else 0

    print(f'ch{ch_num:03d}: "이준" {orig_count}→{new_count} ({reduction}회 감소, {pct:.0f}%)')
    print(f'  분량: {orig_len}→{new_len}자 ({len_pct:+.1f}%)')

    if show_diff:
        orig_lines = text.split('\n')
        new_lines = new_text.split('\n')
        changes = 0
        for j, (o, n) in enumerate(zip(orig_lines, new_lines)):
            if o != n:
                changes += 1
                if changes <= 25:
                    print(f'  L{j+1}: {o.strip()[:80]}')
                    print(f'     → {n.strip()[:80]}')
        print(f'  (총 {changes}줄 변경)')

    out_dir = CHAPTERS_DIR / 'backup_before_polish'
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f'ch{ch_num:03d}_v4_test.md'
    out_path.write_text(new_text, encoding='utf-8')
    print(f'  저장: {out_path}')


if __name__ == '__main__':
    import sys
    ch = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    dry_run(ch)
