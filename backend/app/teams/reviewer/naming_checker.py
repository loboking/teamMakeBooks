"""결정론적 호칭 검수기 — naming_table.md 기반."""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class NamingViolation:
    type: str  # "narration_dialogue_mismatch" / "rule_violation" / "unknown_naming"
    detail: str
    excerpt: str = ""


@dataclass
class NamingCheckResult:
    passed: bool
    score: int
    violations: list[NamingViolation] = field(default_factory=list)
    feedback: str = ""

    def to_review_dict(self) -> dict:
        return {
            "판정": "통과" if self.passed else "반려",
            "점수": self.score,
            "이유": ("호칭 일관성 검증 통과" if self.passed
                    else f"호칭 위반 {len(self.violations)}건"),
            "수정가이드": self.feedback,
        }


# 호칭표 한 줄 패턴: [화자 → 청자]: "호칭" (어조)
_RULE_RE = re.compile(r'\[\s*([^→\[\]]+?)\s*→\s*([^\]\[]+?)\s*\]:\s*"([^"]+)"')

# 서술 호칭 묘사 패턴들 — "X(는|은) (그를|그녀를|이름을) 'Z'(라|이라)(고)? (불|부)..."
_NARR_RE = re.compile(
    r'([\w가-힣]+?)(?:는|은)\s+(?:그를|그녀를|(?:[\w가-힣]+?)(?:을|를))\s*[\'"]([^"\']+?)[\'"](?:라|이라)(?:고)?\s*(?:불렀|부른|부르)'
)
# "X(는|은) Y를 'Z'(라|이라)(고)? 부르..."   더 단순한 형태도 잡기
_NARR_SIMPLE_RE = re.compile(
    r'[\'"]([^"\']+?)[\'"](?:라|이라)(?:고)?\s*불(?:렀|러)'
)

# 대사 추출: 한 줄에 "..." 또는 '...' 형태로 시작하는 큰따옴표 텍스트
_DIALOGUE_RE = re.compile(r'(?<![가-힣\w])"([^"\n]+)"')


def parse_naming_rules(table_text: str) -> dict[tuple[str, str], list[str]]:
    """naming_table.md → {(speaker, listener): [allowed_namings]}."""
    rules: dict[tuple[str, str], list[str]] = {}
    for m in _RULE_RE.finditer(table_text):
        speaker = m.group(1).strip()
        listener = m.group(2).strip()
        naming = m.group(3).strip()
        rules.setdefault((speaker, listener), []).append(naming)
    return rules


def extract_narration_namings(body: str) -> list[tuple[str, str]]:
    """본문 서술 속 '서술자가 명시한 호칭' 추출.
    Returns: [(speaker_name_or_pronoun, alleged_naming), ...]
    """
    found: list[tuple[str, str]] = []
    for m in _NARR_RE.finditer(body):
        speaker = m.group(1).strip()
        naming = m.group(2).strip()
        found.append((speaker, naming))
    return found


def extract_dialogues(body: str) -> list[str]:
    """본문에서 대사들 추출. 큰따옴표 안의 텍스트."""
    return [m.group(1).strip() for m in _DIALOGUE_RE.finditer(body)]


def dialogue_starts_with_address(dialogue: str) -> str | None:
    """대사 시작이 호명인지 판단. '이준 씨, ...' / '오빠, ...' / '강이준,' 등.

    호명 후보: 콤마(,) 또는 느낌표/물음표 직전까지의 1~6자 단어.
    Returns: 호명 문자열 또는 None.
    """
    # "이준 씨," / "오빠!" / "강이준." 등
    m = re.match(r'^([\w가-힣 ]{1,8}?)\s*[,.!?…]\s', dialogue)
    if m:
        candidate = m.group(1).strip()
        # 너무 짧거나 일반어 제외
        if 1 < len(candidate) <= 8:
            return candidate
    return None


def check_narration_dialogue_match(body: str) -> list[NamingViolation]:
    """서술 속 호칭 묘사가 있으면 → 본문 어디에서든 그 호칭이 대사에서 등장해야."""
    violations = []
    narrations = extract_narration_namings(body)
    dialogues = extract_dialogues(body)
    dialogues_text = " ||| ".join(dialogues)

    for speaker, alleged in narrations:
        # alleged 호칭이 대사 어디에도 없으면 위반
        if alleged not in dialogues_text:
            violations.append(NamingViolation(
                type="narration_dialogue_mismatch",
                detail=f"서술이 '{speaker}이(가) 청자를 「{alleged}」(이)라 불렀다'고 묘사했으나, 대사 속에 '{alleged}' 호칭이 등장하지 않음.",
                excerpt=f"서술: {speaker} → '{alleged}'",
            ))
    return violations


def check_direct_rule_violations(
    body: str,
    rules: dict[tuple[str, str], list[str]],
    chapter_n: int,
) -> list[NamingViolation]:
    """대사 시작 호명이 호칭표 룰을 위반하는지 검사.

    제약: 화자/청자를 100% 정확히 추론 못 하므로 다음 휴리스틱 사용.
    - 대사 시작 호명이 호칭표 어딘가에 등장하는 호칭이면 → 매칭된 (화자, 청자) 추정.
    - 그 추정 화자의 모든 룰 중 청자에 대한 호칭이 호명과 일치해야.
    """
    violations: list[NamingViolation] = []
    dialogues = extract_dialogues(body)

    # 모든 호칭 → (화자, 청자) 역인덱스
    naming_to_pairs: dict[str, list[tuple[str, str]]] = {}
    for (sp, ls), names in rules.items():
        for n in names:
            naming_to_pairs.setdefault(n, []).append((sp, ls))

    for dlg in dialogues:
        addr = dialogue_starts_with_address(dlg)
        if addr is None:
            continue
        # 호명이 호칭표 어딘가에 등장하면 OK 후보로 간주.
        if addr in naming_to_pairs:
            continue
        # 등장 안 하는 호명 — 후보 검사: 등장인물 이름과 동일한 직호명
        # (예: "강이준,", "박세린," 등 — 호칭표 비교)
        # 누군가의 호칭표 청자 이름과 일치하면 그 청자에 대한 룰 위반 가능
        for (sp, ls), names in rules.items():
            if addr == ls and addr not in names:
                violations.append(NamingViolation(
                    type="rule_violation",
                    detail=f"대사 호명 '{addr}'이(가) 호칭표상 적절한 호칭이 아님. {sp}가 {ls}를 부른 것이라면 호칭표는 {names} 중 하나여야 함.",
                    excerpt=dlg[:60],
                ))
                break
    return violations


def check_chapter_specific_naming(
    body: str,
    chapter_n: int,
    rules: dict[tuple[str, str], list[str]],
) -> list[NamingViolation]:
    """1막(1~30화)에서 회장이 강이준에게 'F급 군' 외 호칭을 쓰면 위반 등 시점 룰."""
    violations: list[NamingViolation] = []
    if chapter_n <= 30:
        # 1막엔 회장이 강이준을 'F급 군'이라 부름. '강이준 님' 같은 존칭 금지
        forbidden_in_act1 = ["강이준 님", "이준 님"]
        # 본문에 "회장"이 등장하고 그 다음 forbidden 호칭이 일정 거리 내에 있으면 위반
        if "회장" in body:
            for forbidden in forbidden_in_act1:
                if forbidden in body:
                    violations.append(NamingViolation(
                        type="rule_violation",
                        detail=f"1막(현재 {chapter_n}화)에서 회장 등장 + '{forbidden}' 호칭 사용 — 호칭표상 1~2막 초반은 'F급 군'이어야 함.",
                    ))
                    break
    return violations


def check_primary_naming_missing(
    body: str,
    rules: dict[tuple[str, str], list[str]],
) -> list[NamingViolation]:
    """각 (speaker, listener) primary 호칭이 본문에 없는데, secondary가 dialogue 시작 호명으로 빈번하면 위반.

    - primary 호칭이 본문 어디에도 등장하지 않고
    - 같은 페어의 secondary 호칭이 dialogue 시작 호명으로 3회 이상 등장하면 → 위반.
    - 단순 substring count(서술 속 이름 포함)가 아니라 dialogue 시작 호명만 카운트하여 false positive 제거.
    """
    # dialogue 시작 호명만 추출
    dialogues = extract_dialogues(body)
    addresses: list[str] = []
    for d in dialogues:
        addr = dialogue_starts_with_address(d)
        if addr:
            addresses.append(addr)

    violations: list[NamingViolation] = []
    for (sp, ls), names in rules.items():
        if len(names) < 2:
            continue  # primary만 등록된 페어는 검사 X
        primary = names[0]
        if primary in body:
            continue  # primary가 본문에 있으면 OK
        for secondary in names[1:]:
            sec_count = sum(1 for a in addresses if a == secondary)
            if sec_count >= 3:
                violations.append(NamingViolation(
                    type="primary_missing",
                    detail=(
                        f"{sp}→{ls} primary 호칭 '{primary}'이(가) 본문에 없고, "
                        f"secondary 호칭 '{secondary}'이(가) 대사 시작 호명으로 {sec_count}회 사용됨. "
                        f"기본 호칭은 primary를 우선 사용해야 함."
                    ),
                ))
                break  # 같은 페어는 한 번만 보고
    return violations


def run_naming_check(
    body: str,
    naming_table_text: str,
    chapter_n: int,
) -> NamingCheckResult:
    """전체 검수 — 위반이 1건이라도 있으면 반려."""
    rules = parse_naming_rules(naming_table_text)
    violations: list[NamingViolation] = []
    violations.extend(check_narration_dialogue_match(body))
    violations.extend(check_direct_rule_violations(body, rules, chapter_n))
    violations.extend(check_chapter_specific_naming(body, chapter_n, rules))
    violations.extend(check_primary_naming_missing(body, rules))

    if not violations:
        return NamingCheckResult(passed=True, score=10, violations=[], feedback="")

    feedback = "다음 호칭 위반을 수정하라:\n"
    for v in violations[:5]:
        feedback += f"- [{v.type}] {v.detail}\n"
    return NamingCheckResult(
        passed=False,
        score=max(0, 10 - len(violations) * 2),
        violations=violations,
        feedback=feedback.strip(),
    )
