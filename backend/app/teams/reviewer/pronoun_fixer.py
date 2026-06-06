"""결정론적 대명사 성별 치환기 — 캐릭터 gender 메타 기반.

LLM이 생성한 텍스트에서 캐릭터 성별과 대명사가 불일치하는 경우
자동으로 교정한다. LLM 호출 없이 순수 regex 기반.

v2: 문단 경계를 넘어 전체 텍스트를 컨텍스트로 사용.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


# ── 대명사 치환 맵핑 ─────────────────────────────────────────────────────────

PRONOUN_MAP: dict[str, dict[str, str]] = {
    "male_to_female": {
        "그는 ": "그녀는 ",
        "그는\n": "그녀는\n",
        "그의 ": "그녀의 ",
        "그의\n": "그녀의\n",
        "그가 ": "그녀가 ",
        "그가\n": "그녀가\n",
        "그를 ": "그녀를 ",
        "그에게 ": "그녀에게 ",
        "그와 ": "그녀와 ",
    },
    "female_to_male": {
        "그녀는 ": "그는 ",
        "그녀는\n": "그는\n",
        "그녀의 ": "그의 ",
        "그녀의\n": "그의\n",
        "그녀가 ": "그가 ",
        "그녀가\n": "그가\n",
        "그녀를 ": "그를 ",
        "그녀에게 ": "그에게 ",
        "그녀와 ": "그와 ",
    },
}

_MALE_PRONOUNS_RE = re.compile(r"그(는 |의 |가 |를 |에게 |와 |는\n|의\n|가\n)")
_FEMALE_PRONOUNS_RE = re.compile(r"그녀(는 |의 |가 |를 |에게 |와 |는\n|의\n|가\n)")

# 대사 패턴
_DIALOGUE_RE = re.compile(r'"[^"]*"|"[^"]*"')


@dataclass
class PronounFixResult:
    original: str
    fixed: str
    fix_count: int
    details: list[str]


def _build_name_index(characters: list[dict]) -> dict[str, str]:
    """캐릭터 이름/short → gender 매핑 구축."""
    index: dict[str, str] = {}
    for c in characters:
        gender = str(c.get("gender", "")).strip().lower()
        if gender not in ("male", "female"):
            continue
        full = str(c.get("name", "")).strip()
        short = str(c.get("short", "")).strip()
        if full:
            index[full] = gender
        if short and short != full:
            index[short] = gender
    return index


def _find_nearest_character(
    text_up_to_point: str,
    name_index: dict[str, str],
) -> str | None:
    """텍스트에서 가장 마지막에 등장한 캐릭터/성별 명사의 gender 반환.

    일반 성별 명사(남자, 여자, 사람)도 선행사로 인식하여,
    '남자가 앉아 있었다. 그녀는~' 같은 오류를 방지.
    """
    # 일반 성별 명사 매칭
    gender_hints: dict[str, str] = {
        "남자": "male", "남성": "male", "청년": "male",
        "여자": "female", "여성": "female", "소녀": "female",
    }
    # 가장 마지막 줄에서 성별 명사를 찾기
    last_line = text_up_to_point.strip().split('\n')[-1] if text_up_to_point.strip() else ""
    for hint_word, gender in gender_hints.items():
        if hint_word in last_line:
            return gender

    # 캐릭터 이름에서 가장 가까운 것
    last_pos = -1
    last_gender: str | None = None
    for name, gender in name_index.items():
        pos = text_up_to_point.rfind(name)
        if pos > last_pos:
            last_pos = pos
            last_gender = gender
    return last_gender


def fix_gender_pronouns(
    draft: str,
    characters: list[dict],
) -> PronounFixResult:
    """본문 전체에서 성별-대명사 불일치를 결정론적으로 치환.

    v2: 전체 텍스트를 대상으로 대사만 마스킹하고,
    문단 경계에 상관없이 직전의 캐릭터 이름을 선행사로 사용.
    """
    name_index = _build_name_index(characters)
    if not name_index:
        return PronounFixResult(original=draft, fixed=draft, fix_count=0, details=[])

    # 1) 대사 마스킹 — 전체 텍스트에서 한 번에 처리
    placeholders: list[tuple[str, str]] = []
    masked = draft
    idx = 0
    changed = True
    while changed:
        changed = False
        m = _DIALOGUE_RE.search(masked)
        if m:
            key = f"\x00D{idx}\x00"
            placeholders.append((key, m.group()))
            masked = masked[:m.start()] + key + masked[m.end():]
            idx += 1
            changed = True

    # 2) 전체 마스킹된 텍스트에서 대명사 찾아 교정
    #    역순 처리: 뒤에서부터 치환하면 앞의 위치가 어긋나지 않음
    result = masked
    fix_count = 0
    details: list[str] = []

    # 남성 대명사 → 여성 캐릭터 감지 시 치환 (역순)
    for m in reversed(list(_MALE_PRONOUNS_RE.finditer(result))):
        text_before = result[:m.start()]
        gender = _find_nearest_character(text_before, name_index)
        if gender == "female":
            pronoun = m.group()
            replacement = PRONOUN_MAP["male_to_female"].get(pronoun)
            if replacement:
                result = result[:m.start()] + replacement + result[m.end():]
                fix_count += 1
                details.append(f"'{pronoun.strip()}' → '{replacement.strip()}' (여성)")

    # 여성 대명사 → 남성 캐릭터 감지 시 치환 (역순)
    for m in reversed(list(_FEMALE_PRONOUNS_RE.finditer(result))):
        text_before = result[:m.start()]
        gender = _find_nearest_character(text_before, name_index)
        if gender == "male":
            pronoun = m.group()
            replacement = PRONOUN_MAP["female_to_male"].get(pronoun)
            if replacement:
                result = result[:m.start()] + replacement + result[m.end():]
                fix_count += 1
                details.append(f"'{pronoun.strip()}' → '{replacement.strip()}' (남성)")

    # 3) 대사 복원
    for key, original in placeholders:
        result = result.replace(key, original)

    return PronounFixResult(
        original=draft,
        fixed=result,
        fix_count=fix_count,
        details=details,
    )
