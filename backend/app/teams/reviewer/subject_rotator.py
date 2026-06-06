"""결정론적 주어 회전 정제기 — 연속 주어·이름 과다를 regex로 직접 해결.

LLM 호출 없이 순수 문자열 조작으로:
1. 같은 주어 3문장 연속 → 2번째 대명사, 3번째 생략
2. 한 문단 내 이름 과다 → 뒤의 것을 대명사·생략로 교체
3. 대사 내용은 절대 수정하지 않음
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class SubjectFixResult:
    original: str
    fixed: str
    fix_count: int
    details: list[str]


def _build_name_pronoun_map(characters: list[dict]) -> dict[str, str]:
    """이름/short → 성별 대명사 매핑."""
    mapping: dict[str, str] = {}
    for c in characters:
        gender = str(c.get("gender", "")).strip().lower()
        pronoun = "그녀" if gender == "female" else "그" if gender == "male" else "그"
        full = str(c.get("name", "")).strip()
        short = str(c.get("short", "")).strip()
        if full:
            mapping[full] = pronoun
        if short and short != full:
            mapping[short] = pronoun
    return mapping


def _build_short_map(characters: list[dict]) -> dict[str, str]:
    """풀네임 → short 매핑. 참조 모호 방지용 — 대명사 대신 short로 교체."""
    mapping: dict[str, str] = {}
    for c in characters:
        full = str(c.get("name", "")).strip()
        short = str(c.get("short", "")).strip()
        if full and short and full != short:
            mapping[full] = short
    return mapping


def _adjust_particle(name: str, pronoun: str, original_with_particle: str) -> str:
    """이름+조사를 대명사+조사로 교체할 때 조사 형태를 맞춤.

    한국어 받침 규칙:
    - 받침 O + 은/이/을 → 받침 X + 는/가/를
    - 예: 하린(받침O)은 → 그녀(받침X)는
    """
    # 조사 추출
    particle = original_with_particle[len(name):]
    # 대명사의 마지막 글자 받침 여부
    last_char = pronoun[-1] if pronoun else ""
    has_batchim = (ord(last_char) - ord('가')) % 28 != 0 if '가' <= last_char <= '힣' else False

    if not has_batchim:
        # 받침 없으면: 은→는, 이→가, 을→를
        particle = particle.replace('은', '는').replace('이', '가').replace('을', '를')
    return pronoun + particle


def _mask_dialogues(text: str) -> tuple[str, list[tuple[str, str]]]:
    """대사를 placeholder로 마스킹. 반환: (마스킹된 텍스트, [(placeholder, 원본)])"""
    placeholders: list[tuple[str, str]] = []
    result = text
    idx = 0
    # 곧은 따옴표 + 곱따옴표 모두 처리
    for pattern in [r'"[^"]*"', r'“[^”]*”']:
        for m in re.finditer(pattern, result):
            key = f"\x00DLG{idx}\x00"
            placeholders.append((key, m.group()))
            result = result[:m.start()] + key + result[m.end():]
            idx += 1
            break  # finditer는 result가 바뀌면 무효 → 첫 매치만 하고 재시작
    # 남은 대사 전부 처리
    changed = True
    while changed:
        changed = False
        for pattern in [r'"[^"]*"', r'“[^”]*”']:
            for m in re.finditer(pattern, result):
                key = f"\x00DLG{idx}\x00"
                placeholders.append((key, m.group()))
                result = result[:m.start()] + key + result[m.end():]
                idx += 1
                changed = True
                break
            if changed:
                break
    return result, placeholders


def _unmask_dialogues(text: str, placeholders: list[tuple[str, str]]) -> str:
    """placeholder를 원래 대사로 복원."""
    for key, original in placeholders:
        text = text.replace(key, original)
    return text


def _get_subject_pattern(name_map: dict[str, str]) -> re.Pattern:
    """주어 패턴: '하린은', '그녀는', '그는' 등."""
    parts = list(name_map.keys()) + ["그", "그녀"]
    escaped = [re.escape(p) for p in parts]
    return re.compile(rf"^(\s*)((?:{'|'.join(escaped)})(?:은|는|이|가|을|를|의|에게|와|과))\s")


def _build_limit_map(characters: list[dict]) -> dict[str, int]:
    """이름/short별 회차 내 허용 한도 (meta.json limit_* 필드 반영)."""
    limits: dict[str, int] = {}
    for c in characters:
        full = str(c.get("name", "")).strip()
        short = str(c.get("short", "")).strip()
        limit_full = c.get("limit_full", 20)
        limit_short = c.get("limit_short", 0)
        if full and limit_full:
            limits[full] = limit_full
        if short and short != full and limit_short:
            limits[short] = limit_short
    return limits


def rotate_subjects(
    draft: str,
    characters: list[dict],
    *,
    max_consecutive: int = 2,
) -> SubjectFixResult:
    """본문에서 연속 주어와 이름 과다를 결정론적으로 회전.

    Parameters
    ----------
    draft : str
        정제할 본문
    characters : list[dict]
        meta.json의 main_characters (gender, limit_full, limit_short 필드)
    max_consecutive : int
        같은 주어 연속 허용 최대 (기본 2)

    Returns
    -------
    SubjectFixResult
    """
    name_map = _build_name_pronoun_map(characters)
    if not name_map:
        return SubjectFixResult(original=draft, fixed=draft, fix_count=0, details=[])
    short_map = _build_short_map(characters)
    limit_map = _build_limit_map(characters)

    # 1) 대사 마스킹
    masked, placeholders = _mask_dialogues(draft)

    # 2) 전체 본문을 한 흐름으로 처리 — 빈 줄/단락 경계에서 카운트 리셋하지 않음
    subject_re = _get_subject_pattern(name_map)
    fixes = 0
    details: list[str] = []

    prev_subject: str | None = None
    consecutive_count = 0
    fixed_lines: list[str] = []

    for line in masked.split("\n"):
        stripped = line.strip()
        if not stripped:
            fixed_lines.append(line)
            # 빈 줄에서는 카운트 유지 — 단락 경계를 넘는 연속 주어를 잡기 위해
            continue

        # 줄 내 문장 분리
        sentences = re.split(r'(?<=[.!?。])\s+', stripped)
        processed: list[str] = []

        for sentence in sentences:
            m = subject_re.match(sentence)
            if m:
                current_subject = m.group(2)
                subject_base = re.sub(r'(은|는|이|가|을|를|의|에게|와|과)$', '', current_subject)

                if subject_base == prev_subject:
                    consecutive_count += 1
                else:
                    prev_subject = subject_base
                    consecutive_count = 1

                if consecutive_count > max_consecutive:
                    # short가 있으면 short 우선 (참조 모호 방지)
                    replacement = short_map.get(subject_base) or name_map.get(subject_base, "그")
                    if consecutive_count == max_consecutive + 1:
                        new_subject = _adjust_particle(subject_base, replacement, current_subject)
                        new_sentence = m.group(1) + new_subject + " " + sentence[m.end():]
                        if new_sentence != sentence:
                            fixes += 1
                            details.append(f"연속주어: '{current_subject}' → '{new_subject}'")
                            sentence = new_sentence
                            prev_subject = replacement
                    else:
                        new_sentence = m.group(1) + sentence[m.end():]
                        if new_sentence != sentence:
                            fixes += 1
                            details.append(f"주어 생략: '{current_subject}' 제거")
                            sentence = new_sentence
                            consecutive_count = 0
                            prev_subject = None
            else:
                prev_subject = None
                consecutive_count = 0

            processed.append(sentence)

        fixed_lines.append(" ".join(processed))

    fixed_masked = "\n".join(fixed_lines)

    # 3) 회차 전체 이름/short 카운트 → meta.json limit_* 한도 초과분 대명사로 교체
    #    limit_map: {"차하린": 5, "하린": 35, "마린": 20, ...}
    #    중요: short_map이 있는 이름(차하린→하린)을 먼저 처리하면,
    #    새로 생성된 "하린"이 뒤에서 한도 초과로 잡힘.
    #    해결: short 이름을 all_subjects 끝에 배치하여 항상 마지막에 검사.
    all_subjects = list(name_map.keys()) + list(short_map.keys())
    # short 이름(하린, 지원, 채현 등)을 끝으로 이동 — 풀네임→short 교체 후 한도 재검사
    ordered = [n for n in all_subjects if n not in short_map.values()]
    ordered += [n for n in all_subjects if n in short_map.values()]
    # 중복 제거 (preserve order)
    seen: set[str] = set()
    all_subjects = []
    for n in ordered:
        if n not in seen:
            seen.add(n)
            all_subjects.append(n)

    for name in all_subjects:
        if len(name) < 2:
            continue
        limit = limit_map.get(name)
        pronoun = name_map.get(name, "그")
        name_pattern = re.compile(re.escape(name) + r'(은|는|이|가|을|를|의|에게|와|과)')
        occurrences = list(name_pattern.finditer(fixed_masked))
        if not limit or len(occurrences) <= limit:
            continue
        # 초과분을 대명사로 교체
        for occ in reversed(occurrences):
            if len(occurrences) <= limit:
                break
            old = occ.group()
            short_name = short_map.get(name)
            if short_name:
                new = _adjust_particle(name, short_name, old)
            else:
                new = _adjust_particle(name, pronoun, old)
            fixed_masked = fixed_masked[:occ.start()] + new + fixed_masked[occ.end():]
            fixes += 1
            details.append(f"회차 한도 초과 ({name} limit={limit}): '{old}' → '{new}'")
            occurrences = occurrences[:-1]

    # 3.5) Phase 3 보정 패스 — 풀네임→short 교체로 새로 생긴 short 이름이
    #       한도를 초과할 수 있으므로, short 이름만 한 번 더 검사.
    for name in list(short_map.values()):
        limit = limit_map.get(name)
        if not limit:
            continue
        pronoun = name_map.get(name, "그")
        name_pattern = re.compile(re.escape(name) + r'(은|는|이|가|을|를|의|에게|와|과)')
        occurrences = list(name_pattern.finditer(fixed_masked))
        if len(occurrences) <= limit:
            continue
        for occ in reversed(occurrences):
            if len(occurrences) <= limit:
                break
            old = occ.group()
            new = _adjust_particle(name, pronoun, old)
            fixed_masked = fixed_masked[:occ.start()] + new + fixed_masked[occ.end():]
            fixes += 1
            details.append(f"한도 보정 ({name} limit={limit}): '{old}' → '{new}'")
            occurrences = occurrences[:-1]

    # 3.6) 대명사(그녀/그) 한도 검사 — pronoun_fix가 대량 치환한 경우 과다 방지
    _PRONOUN_LIMIT = 30
    for pronoun_target in ["그녀", "그"]:
        pronoun_pattern = re.compile(re.escape(pronoun_target) + r'(는|가|를|의|에게|와|과)')
        occurrences = list(pronoun_pattern.finditer(fixed_masked))
        if len(occurrences) <= _PRONOUN_LIMIT:
            continue
        for occ in reversed(occurrences):
            if len(occurrences) <= _PRONOUN_LIMIT:
                break
            old = occ.group()
            # 대명사 초과분은 주어 생략 (조사만 제거)
            fixed_masked = fixed_masked[:occ.start()] + fixed_masked[occ.end():]
            fixes += 1
            details.append(f"대명사 한도 ({pronoun_target} limit={_PRONOUN_LIMIT}): '{old}' 생략")
            occurrences = occurrences[:-1]

    # 4) 대사 복원
    fixed = _unmask_dialogues(fixed_masked, placeholders)

    return SubjectFixResult(
        original=draft,
        fixed=fixed,
        fix_count=fixes,
        details=details,
    )


def _fix_paragraph(
    paragraph: str,
    name_map: dict[str, str],
    *,
    max_consecutive: int,
    max_per_paragraph: int,
) -> tuple[str, int, list[str]]:
    """단일 문단에서 연속 주어 회전 + 이름 과다 교체."""
    if not paragraph.strip():
        return paragraph, 0, []

    subject_re = _get_subject_pattern(name_map)
    fixes = 0
    details: list[str] = []
    result = paragraph

    # ── Phase 1: 연속 주어 회전 ──
    # 문장 분리 (마침표/물음표/느낌표 + 공백)
    sentences = re.split(r'(?<=[.!?。])\s+', result)
    prev_subject: str | None = None
    consecutive_count = 0
    processed: list[str] = []

    for sentence in sentences:
        m = subject_re.match(sentence)
        if m:
            current_subject = m.group(2)  # "하린은", "그녀는" 등
            # 주어의 핵심(조사 제거 전) 추출
            subject_base = re.sub(r'(은|는|이|가|을|를|의|에게|와|과)$', '', current_subject)

            if subject_base == prev_subject:
                consecutive_count += 1
            else:
                prev_subject = subject_base
                consecutive_count = 1

            if consecutive_count > max_consecutive:
                # 대명사로 교체 또는 주어 생략
                pronoun = name_map.get(subject_base, "그")
                if consecutive_count == max_consecutive + 1:
                    # 대명사로 교체 (조사 교정 포함)
                    new_subject = _adjust_particle(subject_base, pronoun, current_subject)
                    new_sentence = m.group(1) + new_subject + " " + sentence[m.end():]
                    if new_sentence != sentence:
                        fixes += 1
                        details.append(f"연속주어: '{current_subject}' → '{new_subject}'")
                        sentence = new_sentence
                        prev_subject = pronoun  # 다음 비교는 대명사 기준
                else:
                    # 주어 생략
                    new_sentence = m.group(1) + sentence[m.end():]
                    if new_sentence != sentence:
                        fixes += 1
                        details.append(f"주어 생략: '{current_subject}' 제거")
                        sentence = new_sentence
                        # 생략 후엔 연속 카운트 리셋
                        consecutive_count = 0
                        prev_subject = None
        else:
            # 주어 없는 문장 — 연속 카운트 리셋
            prev_subject = None
            consecutive_count = 0

        processed.append(sentence)

    result = " ".join(processed)

    # ── Phase 2: 한 문단 내 이름 과다 → 대명사 교체 ──
    for name, pronoun in name_map.items():
        # 이 문단에서 해당 이름(조사 포함) 출현 횟수
        name_pattern = re.compile(re.escape(name) + r'(은|는|이|가|을|를|의|에게|와|과)')
        occurrences = list(name_pattern.finditer(result))
        if len(occurrences) > max_per_paragraph:
            # max_per_paragraph 이후부터 대명사로 교체 (조사 교정 포함)
            for occ in occurrences[max_per_paragraph:]:
                old = occ.group()
                new = _adjust_particle(name, pronoun, old)
                result = result[:occ.start()] + new + result[occ.end():]
                fixes += 1
                details.append(f"이름과다: '{old}' → '{new}'")
                # result가 바뀌었으므로 이후 occ 위치가 어긋날 수 있음
                # → 간단히 첫 번째 과다분만 교체하고 재검사는 다음 파이프라인 반복에 맡김
                break

    return result, fixes, details
