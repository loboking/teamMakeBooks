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

# 맥락 조건 파싱: "1막~2막 초반", "2막 후반~", "4막 클라이맥스", "3막 만남 직후"
_CONTEXT_RANGE_RE = re.compile(
    r'(\d+)막\s*(?:초반|전반|후반|중반)?\s*(?:~|부터|부터)?\s*(?:(\d+)막)?\s*(초반|후반|중반|클라이맥스|만남 직후)?'
)

# ── 막 정의 ──────────────────────────────────────────────────────────────────

ACT_RANGES: dict[str, tuple[int, int]] = {
    "1막": (1, 30),
    "2막 초반": (31, 50),
    "2막 전반": (31, 50),
    "2막 후반": (51, 65),
    "2막 중반": (45, 55),
    "3막": (66, 90),
    "3막 초반": (66, 75),
    "3막 후반": (76, 90),
    "3막 만남 직후": (76, 90),
    "4막": (91, 100),
    "4막 초기": (91, 95),
    "4막 클라이맥스": (96, 100),
    "4막 만남 직후": (91, 95),
}


def _parse_context_range(context: str) -> tuple[int, int] | None:
    """호칭표의 맥락 조건에서 적용 회차 범위를 파싱.

    Returns (start_ch, end_ch) 또는 None (전체 적용).
    """
    if not context:
        return None

    context = context.strip()

    # "X막~Y막 Z" 패턴 파싱
    m = _CONTEXT_RANGE_RE.match(context)
    if not m:
        # 범위 지정이 없으면 전체 적용
        return None

    start_act = f"{m.group(1)}막"
    # "초반/전반/후반/중반" 수식어가 있으면 포함
    start_qualifier = m.group(2)
    if start_qualifier:
        start_act = f"{m.group(1)}막 {start_qualifier}"

    start = ACT_RANGES.get(start_act)
    if start is None:
        # "2막" 같이 수식어 없는 기본값
        start = ACT_RANGES.get(f"{m.group(1)}막")

    if start is None:
        return None

    end = start  # 기본: 시작과 같은 막
    if m.group(3):  # 두 번째 막 번호
        end_act = f"{m.group(3)}막"
        end_qualifier = m.group(4)
        if end_qualifier:
            end_act = f"{m.group(3)}막 {end_qualifier}"
        end = ACT_RANGES.get(end_act, start)

    return (start[0], end[1])


def _context_matches(context: str, chapter_n: int) -> bool:
    """맥락 조건이 현재 회차에 적용되는지 확인."""
    if not context:
        return True  # 조건 없으면 항상 적용
    ch_range = _parse_context_range(context)
    if ch_range is None:
        return True  # 파싱 실패면 안전하게 적용
    return ch_range[0] <= chapter_n <= ch_range[1]


def _character_appears(speaker: str, body: str) -> bool:
    """해당 화자(또는 청자)가 본문에 등장하는지 간이 확인.

    캐릭터 이름이 본문에 한 번 이상 등장하면 등장한 것으로 간주.
    """
    if not speaker:
        return False
    # 화자/청자 이름에서 공백/접미사 제거 후 2자 이상 핵심 이름 추출
    clean = re.sub(r'\s+', '', speaker.strip())
    if len(clean) < 2:
        return True  # 너무 짧으면 무시
    # 본문에 이름이 등장하는지 확인
    return clean in body


# ── 기존 파싱 함수 ────────────────────────────────────────────────────────────


def parse_naming_rules(table_text: str) -> list[dict]:
    """naming_table.md → [{speaker, listener, naming, context}, ...] 맥락 포함."""
    rules: list[dict] = []
    for m in _RULE_RE.finditer(table_text):
        speaker = m.group(1).strip()
        listener = m.group(2).strip()
        naming = m.group(3).strip()
        # 맥락 조건: 라인 전체에서 괄호 안의 텍스트 추출
        line = m.string[m.start():m.end()]
        ctx_match = re.search(r'\(([^)]+)\)', line)
        context = ctx_match.group(1) if ctx_match else ""
        rules.append({
            "speaker": speaker,
            "listener": listener,
            "naming": naming,
            "context": context,
        })
    return rules


def extract_narration_namings(body: str) -> list[tuple[str, str]]:
    """본문 서술 속 '서술자가 명시한 호칭' 추출."""
    found: list[tuple[str, str]] = []
    for m in _NARR_RE.finditer(body):
        speaker = m.group(1).strip()
        naming = m.group(2).strip()
        found.append((speaker, naming))
    return found


def extract_dialogues(body: str) -> list[str]:
    """본문에서 대사들 추출."""
    return [m.group(1).strip() for m in _DIALOGUE_RE.finditer(body)]


def dialogue_starts_with_address(dialogue: str) -> str | None:
    """대사 시작이 호명인지 판단.

    제외: "이름." 패턴(3인칭 서술 중심 회상에서 흔한)은 호명이 아닌 문장 시작.
    """
    # "이름." 패턴 제외 — 세린: "도서윤. v1.9, S급?" 같은 회상/제시는 호명 아님
    m = re.match(r'^([\w가-힣 ]{1,8}?)\.\s', dialogue)
    if m:
        # 마침표 직후에 데이터(숫자, v1.9 등)가 오면 호명이 아닌 서술
        rest = dialogue[m.end():]
        if rest and (rest[0].isdigit() or rest[:2] in ('v1', 'v2')):
            return None
    m = re.match(r'^([\w가-힣 ]{1,8}?)\s*[,.!?…]\s', dialogue)
    if m:
        candidate = m.group(1).strip()
        if 1 < len(candidate) <= 8:
            return candidate
    return None


# ── 검사 함수들 ──────────────────────────────────────────────────────────────


def check_narration_dialogue_match(body: str) -> list[NamingViolation]:
    """서술 속 호칭 묘사가 있으면 → 본문 어디에서든 그 호칭이 대사에서 등장해야."""
    violations = []
    narrations = extract_narration_namings(body)
    dialogues = extract_dialogues(body)
    dialogues_text = " ||| ".join(dialogues)

    for speaker, alleged in narrations:
        if alleged not in dialogues_text:
            violations.append(NamingViolation(
                type="narration_dialogue_mismatch",
                detail=f"서술이 '{speaker}이(가) 청자를 「{alleged}」(이)라 불렀다'고 묘사했으나, 대사 속에 '{alleged}' 호칭이 등장하지 않음.",
                excerpt=f"서술: {speaker} → '{alleged}'",
            ))
    return violations


def check_direct_rule_violations(
    body: str,
    rules: list[dict],
    chapter_n: int,
) -> list[NamingViolation]:
    """대사 시작 호명이 현재 회차에 적용되는 호칭표 룰을 위반하는지 검사."""
    violations: list[NamingViolation] = []
    dialogues = extract_dialogues(body)

    # 맥락 조건 필터링: 현재 회차에 적용되는 규칙만
    active_rules = [r for r in rules if _context_matches(r["context"], chapter_n)]

    # 등장 인물 필터링: 화자나 청자가 본문에 없으면 제외
    active_rules = [r for r in active_rules
                     if _character_appears(r["speaker"], body) or _character_appears(r["listener"], body)]

    # 모든 호칭 → (화자, 청자) 역인덱스
    naming_to_pairs: dict[str, list[tuple[str, str]]] = {}
    for r in active_rules:
        naming_to_pairs.setdefault(r["naming"], []).append((r["speaker"], r["listener"]))

    for dlg in dialogues:
        addr = dialogue_starts_with_address(dlg)
        if addr is None:
            continue
        if addr in naming_to_pairs:
            continue
        # 등장 인물 이름과 일치하는 직호명
        for r in active_rules:
            if addr == r["listener"] and addr not in r["naming"]:
                violations.append(NamingViolation(
                    type="rule_violation",
                    detail=f"대사 호명 '{addr}'이(가) 호칭표상 적절한 호칭이 아님. {r['speaker']}가 {r['listener']}를 부른 것이라면 호칭표는 '{r['naming']}'이어야 함.",
                    excerpt=dlg[:60],
                ))
                break
    return violations


def check_chapter_specific_naming(
    body: str,
    chapter_n: int,
    rules: list[dict],
) -> list[NamingViolation]:
    """1막(1~30화)에서 회장이 강이준에게 'F급 군' 외 호칭을 쓰면 위반 등 시점 룰."""
    violations: list[NamingViolation] = []
    if chapter_n <= 30:
        forbidden_in_act1 = ["강이준 님", "이준 님"]
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
    rules: list[dict],
    chapter_n: int,
) -> list[NamingViolation]:
    """현재 회차에 적용되는 규칙에서만 primary 호칭 누락 검사."""
    # 맥락 조건 필터링
    active_rules = [r for r in rules if _context_matches(r["context"], chapter_n)]

    # 등장 인물 필터링
    active_rules = [r for r in active_rules
                     if _character_appears(r["speaker"], body) or _character_appears(r["listener"], body)]

    # (speaker, listener)별로 그룹화
    grouped: dict[tuple[str, str], list[dict]] = {}
    for r in active_rules:
        key = (r["speaker"], r["listener"])
        grouped.setdefault(key, []).append(r)

    # dialogue 시작 호명만 추출
    dialogues = extract_dialogues(body)
    addresses: list[str] = []
    for d in dialogues:
        addr = dialogue_starts_with_address(d)
        if addr:
            addresses.append(addr)

    violations: list[NamingViolation] = []
    for (sp, ls), names in grouped.items():
        if len(names) < 2:
            continue
        primary = names[0]["naming"]
        if primary in body:
            continue
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
                break
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
    violations.extend(check_primary_naming_missing(body, rules, chapter_n))

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
