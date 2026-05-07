"""메타 작가 프롬프트 + JSON 스키마.

세 단계: 컨셉 정규화 / 엔딩+3막 / 막 단위 100화 줄거리.
모든 출력은 ollama format_schema로 강제. gemma4:e2b 짧은 컨텍스트에 맞춰
프롬프트는 짧게, 학습 예시는 1~2개씩만.

작품 톤 약속:
- 게임표준어 유지: 마나·길드·던전·헌터 (외래어 그대로)
- 한글로 변환: 어쌔신·탱커·스탯 약어 (DEX/STR 등)
- 100화 종결 가정 (1막 1~33 / 2막 34~67 / 3막 68~100)
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# JSON 스키마 — ollama format_schema 강제용
# ---------------------------------------------------------------------------

CONCEPT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "logline": {"type": "string"},
        "genre": {"type": "string"},
        "mood": {"type": "string"},
        "total_chapters": {"type": "integer"},
        "protagonist": {"type": "string"},
        "keywords": {"type": "array", "items": {"type": "string"}},
        "forbidden": {"type": "array", "items": {"type": "string"}},
        "reference_tone": {"type": "string"},
        "summary": {"type": "string"},
    },
    "required": [
        "logline", "genre", "mood", "total_chapters",
        "protagonist", "keywords", "forbidden", "reference_tone", "summary",
    ],
}


ENDING_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "act3_climax": {"type": "string"},
        "acts": {
            "type": "array",
            "minItems": 3,
            "maxItems": 3,
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "range": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "minItems": 2,
                        "maxItems": 2,
                    },
                    "summary": {"type": "string"},
                    "climax": {"type": "string"},
                },
                "required": ["name", "range", "summary", "climax"],
            },
        },
    },
    "required": ["summary", "act3_climax", "acts"],
}


PLOT_ACT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "chapters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "chapter_n": {"type": "integer"},
                    "act": {"type": "integer"},
                    "overall": {"type": "string"},
                },
                "required": ["chapter_n", "act", "overall"],
            },
        }
    },
    "required": ["chapters"],
}


# 단일 화 — 화별 1회 호출용 (긴 JSON 배열 출력 한계 회피)
PLOT_CHAPTER_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "chapter_n": {"type": "integer"},
        "act": {"type": "integer"},
        "overall": {"type": "string"},
    },
    "required": ["chapter_n", "act", "overall"],
}


# 비트 확장 — overall(200~300자) → beats[3] (각 instruction 1,800자+)
BEAT_EXPAND_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "beats": {
            "type": "array",
            "minItems": 3,
            "maxItems": 3,
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "instruction": {"type": "string"},
                },
                "required": ["name", "instruction"],
            },
        }
    },
    "required": ["beats"],
}


# 사전 자산 — 작품 단위 1회 호출용 스키마들
WORLD_BIBLE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "content": {"type": "string"},  # markdown 전체
    },
    "required": ["content"],
}

CHARACTERS_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "characters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "role": {"type": "string"},      # 주인공/조력자/적대자/조연
                    "rank": {"type": "string"},      # F~S (해당 없으면 빈 문자열)
                    "job": {"type": "string"},
                    "personality": {"type": "string"},
                    "appearance": {"type": "string"},
                    "background": {"type": "string"},
                    "arc": {"type": "string"},
                },
                "required": ["name", "role", "personality", "arc"],
            },
        },
    },
    "required": ["characters"],
}

NAMING_TABLE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "pairs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "speaker": {"type": "string"},
                    "listener": {"type": "string"},
                    "address": {"type": "string"},
                    "context": {"type": "string"},
                },
                "required": ["speaker", "listener", "address"],
            },
        },
    },
    "required": ["pairs"],
}

PERSONA_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "name": {"type": "string"},
        "genre": {"type": "string"},
        "style": {"type": "string"},
        "tone": {"type": "string"},
        "favorite_tropes": {"type": "array", "items": {"type": "string"}},
        "avoid": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["id", "name", "genre", "style", "tone"],
}


# ---------------------------------------------------------------------------
# 공통 톤 블록 — 모든 메타 작가 프롬프트에 삽입
# ---------------------------------------------------------------------------

TONE_RULES = (
    "[작품 톤 약속 — 모든 단계에서 반드시 지킨다]\n"
    "- 게임표준어 유지: 마나, 길드, 던전, 헌터 (한글 변환 금지)\n"
    "- 한글로 변환: 어쌔신, 탱커, 스탯 약어(DEX/STR 등)\n"
    "- 100화 완결 구조 가정 (1막 1~33 / 2막 34~67 / 3막 68~100)\n"
    "- 한국 웹소설 톤: 시니컬·건조·타격감 / 신파 미사여구 금지\n"
    "- 유저는 이미 인물·세계관을 알고 있다 — 회차 줄거리에 인물 소개 반복 금지\n"
)


# ---------------------------------------------------------------------------
# 1단계: 컨셉 정규화
# ---------------------------------------------------------------------------

def _format_concept_input(ci: dict) -> str:
    """사용자 입력 dict을 프롬프트용 텍스트로 직렬화."""
    lines = []
    for key in (
        "logline", "genre", "mood", "total_chapters",
        "protagonist", "keywords", "forbidden", "reference_tone",
    ):
        v = ci.get(key)
        if v is None or v == "" or v == []:
            continue
        if isinstance(v, list):
            v = ", ".join(str(x) for x in v)
        lines.append(f"- {key}: {v}")
    return "\n".join(lines) if lines else "- (입력 없음)"


def build_concept_prompt(concept_input: dict, work_id: str) -> str:
    """사용자 입력을 정규화 + 누락 옵션 보충 + summary 3~5줄 생성."""
    raw = _format_concept_input(concept_input)
    return (
        "[메타 작가 — 1단계: 컨셉 정규화]\n\n"
        f"{TONE_RULES}\n"
        "[과제]\n"
        "사용자가 던진 컨셉 입력을 정리해 작품의 컨셉 카드를 만든다.\n"
        "- 누락 항목은 logline에서 합리적으로 추론해 채운다.\n"
        "- total_chapters가 비어 있으면 100으로 둔다.\n"
        "- summary는 작품을 처음 듣는 작가가 톤·세계관·핵심 갈등을 즉시 잡을 수 있도록 3~5줄.\n"
        "- keywords는 장르·소재 태그 3~6개. forbidden은 사용자가 명시 안 했으면 빈 배열.\n"
        "- reference_tone이 비어 있으면 빈 문자열로.\n"
        f"- work_id는 '{work_id}'로 고정 — 이건 별도 시스템이 결정했으니 출력에는 포함하지 않는다.\n\n"
        "[학습 예시 — 통과]\n"
        "입력:\n"
        "- logline: F급 짐꾼이 시스템 버그를 발견해 S급으로 각성\n"
        "- genre: 헌터물\n"
        "- mood: 다크코미디\n"
        "- protagonist: 강이준\n"
        "출력:\n"
        '{"logline":"F급 짐꾼이 시스템 버그를 발견해 S급으로 각성",'
        '"genre":"헌터물","mood":"다크코미디","total_chapters":100,'
        '"protagonist":"강이준","keywords":["시스템물","각성물","길드정치"],'
        '"forbidden":[],"reference_tone":"",'
        '"summary":"만년 F급 짐꾼 강이준이 던전 사고로 시스템 버그를 발견해 진짜 등급을 숨긴 채 S급으로 성장한다. '
        '길드 정치와 거대 자본의 회유·압박이 이어지는 가운데 동료들과 연합해 시스템 자체의 진실을 추적한다. '
        '톤은 시니컬한 다크코미디, 100화 완결 구조."}\n\n'
        "[사용자 입력]\n"
        f"{raw}\n\n"
        "[출력 — 위 JSON 스키마를 정확히. 다른 텍스트 절대 금지.]"
    )


def build_concept_revise_prompt(concept: dict, feedback: str, work_id: str) -> str:
    """기존 컨셉 + 검수자 피드백 → 재생성."""
    cur = _format_concept_input(concept)
    cur_summary = concept.get("summary", "")
    return (
        "[메타 작가 — 1단계 재생성: 컨셉 정규화]\n\n"
        f"{TONE_RULES}\n"
        "[기존 컨셉]\n"
        f"{cur}\n"
        f"- summary: {cur_summary}\n\n"
        "[검수자 피드백]\n"
        f"{feedback.strip()}\n\n"
        "[수정 지시]\n"
        "- 피드백을 반영해 컨셉 카드를 다시 작성한다.\n"
        "- protagonist·logline 핵심은 사용자 의도가 명확하지 않으면 유지.\n"
        f"- work_id는 '{work_id}' 고정 (출력에 포함하지 않음).\n\n"
        "[출력 — 위 JSON 스키마를 정확히. 다른 텍스트 절대 금지.]"
    )


# ---------------------------------------------------------------------------
# 2단계: 엔딩 + 3막 골격
# ---------------------------------------------------------------------------

def _format_concept_block(concept: dict) -> str:
    """엔딩/플롯 단계에서 컨셉 dict을 압축 직렬화."""
    keywords = ", ".join(concept.get("keywords", []) or []) or "—"
    forbidden = ", ".join(concept.get("forbidden", []) or []) or "—"
    return (
        f"- logline: {concept.get('logline', '')}\n"
        f"- genre: {concept.get('genre', '')}\n"
        f"- mood: {concept.get('mood', '')}\n"
        f"- protagonist: {concept.get('protagonist', '')}\n"
        f"- total_chapters: {concept.get('total_chapters', 100)}\n"
        f"- keywords: {keywords}\n"
        f"- forbidden: {forbidden}\n"
        f"- summary: {concept.get('summary', '')}\n"
    )


def build_ending_prompt(concept: dict, work_id: str) -> str:
    """엔딩 1줄 + 3막 골격(33/34/33). gemma4가 각 막에 1~2줄씩만 쓰게."""
    total = int(concept.get("total_chapters", 100))
    # 100화 가정 → 1~33 / 34~67 / 68~100. 다른 길이는 round 균등 분할.
    a1_end = round(total / 3)
    a2_end = round(total * 2 / 3)
    a1 = (1, a1_end)
    a2 = (a1_end + 1, a2_end)
    a3 = (a2_end + 1, total)

    return (
        "[메타 작가 — 2단계: 엔딩 + 3막 골격]\n\n"
        f"{TONE_RULES}\n"
        "[컨셉]\n"
        f"{_format_concept_block(concept)}\n"
        "[과제]\n"
        f"총 {total}화 완결 구조의 북극성. 모든 회차 작가가 이 엔딩을 향해 글을 쓴다.\n"
        "- summary: 작품의 마지막 장면을 1줄로 못 박는다 (분위기·관계·핵심 결정만).\n"
        "- act3_climax: 3막 클라이맥스(=작품 정점)를 1~2줄로.\n"
        "- acts는 반드시 3개:\n"
        f"  · 1막 range=[{a1[0]},{a1[1]}], 2막 range=[{a2[0]},{a2[1]}], 3막 range=[{a3[0]},{a3[1]}]\n"
        "  · 각 막 summary 2~3줄: 그 막에서 일어나는 핵심 사건·관계 변화·세계 변화.\n"
        "  · 각 막 climax 1줄: 그 막의 마지막 페이지에서 독자에게 던지는 충격·전환점.\n"
        "- 1막은 '발단·각성', 2막은 '대립·확장', 3막은 '결착·승화' 흐름.\n"
        "- 절대 금지: 인물 소개 반복, 배경 설명 늘어놓기, 회차 비트 단위로 쪼개기. 막 단위 압축만.\n\n"
        "[학습 예시 — 통과]\n"
        "컨셉(요약): F급 짐꾼이 시스템 버그로 S급 각성, 다크코미디 헌터물, 100화\n"
        "출력:\n"
        '{"summary":"만년 F급 짐꾼이었던 그가 시스템의 새 관리자가 되어 햇빛 속으로 걸어 나간다.",'
        '"act3_climax":"감독자 처단 후 강이준이 시스템 핵심 통제권을 인계받는 카타르시스 장면.",'
        '"acts":['
        '{"name":"1막","range":[1,33],"summary":"D급 던전 추락으로 진명 시스템 각성. '
        '능력을 숨긴 채 짐꾼 신분 유지하며 첫 성장. 박세린이 의심을 시작한다.",'
        '"climax":"길드 임무 중 능력 일부 노출. 박세린이 그를 직시하며 \'이준 씨, 너 뭐야?\'"},'
        '{"name":"2막","range":[34,67],"summary":"박세린에게 일부 비밀 공유. 거대 길드 백화의 회유와 압박. '
        '회장 직접 등장. 강이준 가족이 표적이 된다.","climax":"회장이 강이준에게 \'곧 잘못을 바로잡아야겠군\' 최후통첩."},'
        '{"name":"3막","range":[68,100],"summary":"진명 시스템 보유자 윤새벽·도서윤 합류. 백화 본부 침투, 회장 처단. '
        '감독자의 정체와 시스템 진실이 드러난다. 최종 대결.",'
        '"climax":"감독자 처단 후 강이준이 시스템 통제권을 받아 \'무등급(Beyond Rank)\'이 된다."}'
        "]}\n\n"
        "[출력 — 위 JSON 스키마를 정확히. 다른 텍스트 절대 금지.]"
    )


def build_ending_revise_prompt(ending: dict, feedback: str, concept: dict, work_id: str) -> str:
    """엔딩+3막 재생성. 기존 결과 + 피드백 + 컨셉을 모두 받음."""
    import json as _json
    cur = _json.dumps(ending, ensure_ascii=False, indent=2)
    return (
        "[메타 작가 — 2단계 재생성: 엔딩 + 3막 골격]\n\n"
        f"{TONE_RULES}\n"
        "[컨셉]\n"
        f"{_format_concept_block(concept)}\n"
        "[기존 엔딩+3막]\n"
        f"{cur}\n\n"
        "[검수자 피드백]\n"
        f"{feedback.strip()}\n\n"
        "[수정 지시]\n"
        "- 피드백을 반영해 엔딩과 3막 골격을 다시 짠다.\n"
        "- 컨셉(logline·protagonist·mood)은 절대 바꾸지 않는다.\n"
        "- 막 range는 입력 컨셉 기준 균등 분할 유지.\n\n"
        "[출력 — 위 JSON 스키마를 정확히. 다른 텍스트 절대 금지.]"
    )


# ---------------------------------------------------------------------------
# 3단계: 막 단위 100화 줄거리 (33~34화/막, 화별 200~300자)
# ---------------------------------------------------------------------------

def _format_ending_block(ending: dict) -> str:
    """플롯 단계에서 엔딩 dict 압축 직렬화."""
    out = [f"- 엔딩(작품 마지막 장면): {ending.get('summary', '')}"]
    out.append(f"- 3막 클라이맥스: {ending.get('act3_climax', '')}")
    for a in ending.get("acts", []) or []:
        rng = a.get("range", [0, 0])
        out.append(
            f"- {a.get('name','')} [{rng[0]}~{rng[1]}화] | "
            f"요약: {a.get('summary','')} | "
            f"클라이맥스: {a.get('climax','')}"
        )
    return "\n".join(out)


def build_plot_act_prompt(
    concept: dict, ending: dict, *, act_idx: int, work_id: str,
) -> str:
    """막 1개(33~34화)의 회차별 overall을 한 번에 생성.

    각 화 overall은 200~300자. 짧으면 검수에서 반려된다.
    """
    acts = ending.get("acts", [])
    if not (0 <= act_idx < len(acts)):
        raise ValueError(f"act_idx 범위 초과: {act_idx}")
    act = acts[act_idx]
    rng = act.get("range", [1, 1])
    start, end = int(rng[0]), int(rng[1])
    n_chapters = end - start + 1
    act_no = act_idx + 1

    return (
        f"[메타 작가 — 3단계: {act.get('name', f'{act_no}막')} 회차별 줄거리]\n\n"
        f"{TONE_RULES}\n"
        "[컨셉]\n"
        f"{_format_concept_block(concept)}\n"
        "[엔딩 + 3막 골격 — 변경 절대 금지]\n"
        f"{_format_ending_block(ending)}\n\n"
        "[과제]\n"
        f"{act.get('name', f'{act_no}막')}({start}화~{end}화 = 총 {n_chapters}화)의 "
        f"회차별 overall 줄거리를 정확히 {n_chapters}개 생성한다.\n"
        f"- 각 chapters 항목: chapter_n(={start}~{end} 정수, 순서대로), act(={act_no}), overall.\n"
        "- overall 분량: **각 화 200~300자**. 회차 작가가 이걸 보고 비트 3개로 쪼개 5,000자 본문을 쓴다.\n"
        "- overall 작성 룰:\n"
        "  · 핵심 사건 1~2개 + 감정/긴장 변화 1개 + 다음 회로 넘기는 후크.\n"
        "  · '강이준은 F급 짐꾼이다' 같은 인물 소개 반복 금지. 이미 안다.\n"
        "  · 등급·직업 설명 반복 금지. 새 사건·새 정보·새 갈등만.\n"
        "  · 같은 사건을 두 화에 걸쳐 평탄하게 늘이지 마라. 매 화 한 걸음 전진.\n"
        "  · 막 마지막 화는 막 climax를 정확히 친다.\n"
        "- 진행 곡선: 막 안에서 도입(1/3) → 가속(1/3) → 막 climax(마지막) 곡선을 의식한다.\n\n"
        "[학습 예시 — 1막 첫 3화 (참고용 톤·길이)]\n"
        '{"chapters":['
        '{"chapter_n":1,"act":1,"overall":"강이준이 만년 F급 짐꾼으로 D급 던전 임무에 투입된다. '
        '동료들이 보스를 잡는 동안 후방에서 짐을 끌다 천장 붕괴로 던전 심층부에 추락한다. '
        '동료들은 그를 죽었다 여기고 떠나고, 어둠 속에서 깨어난 그의 눈앞에 푸른 시스템 창이 떠오른다. '
        '진명 시스템 각성. 첫 퀘스트 \'이 던전에서 살아 나가라\'를 받고 발걸음을 내딛는 순간, '
        '어둠 속에서 거대한 무언가의 윤곽이 드러난다."},'
        '{"chapter_n":2,"act":1,"overall":"강이준이 시스템 안내에 따라 던전 심층부의 거대 몬스터와 첫 전투에 돌입한다. '
        '스탯 LV1·빈 스킬창·고장난 단검 한 자루로 시작하는 사투. 진명 시스템이 약점 정보를 실시간으로 분석해주며 '
        '첫 처치에 성공하지만 부상은 깊다. 시체 옆에서 발견한 의문의 메모 한 장, '
        '시스템의 진짜 정체를 암시하는 첫 단서가 그의 손에 들어온다."},'
        '{"chapter_n":3,"act":1,"overall":"보상 경험치로 첫 레벨업과 스킬 한 종을 획득한 강이준이 던전 외부로 탈출을 시도한다. '
        '능력을 모두 숨긴 채 \'운 좋게 살아남은 짐꾼\'으로 위장하기로 결심한다. '
        '입구를 막는 마지막 몬스터를 \'우연한 사고\'로 처리하는 묘사. 햇빛 아래로 기어나온 그를 발견한 박세린의 표정이 굳는다. '
        '\'분명 죽었다고 했는데\' — 그녀의 의심이 시작되는 순간."}]}\n\n'
        "[출력 — 위 JSON 스키마를 정확히. 다른 텍스트 절대 금지. "
        f"chapters 배열 길이는 정확히 {n_chapters}.]"
    )


def build_plot_chapter_prompt(
    concept: dict, ending: dict,
    *, act_idx: int, chapter_n: int,
    prev_chapters: list[dict] | None = None,
    work_id: str,
) -> str:
    """단일 화의 overall(200~300자)만 생성. 직전 1~2화를 컨텍스트로 받음.

    회차 작가의 비트 단위 호출과 같은 패턴 — 작은 호출 N번이 긴 배열보다 안정적.
    """
    acts = ending.get("acts", [])
    if not (0 <= act_idx < len(acts)):
        raise ValueError(f"act_idx 범위 초과: {act_idx}")
    act = acts[act_idx]
    rng = act.get("range", [1, 1])
    start, end = int(rng[0]), int(rng[1])
    act_no = act_idx + 1
    is_first = chapter_n == start
    is_last = chapter_n == end

    prev_block = ""
    if prev_chapters:
        items = []
        for p in prev_chapters[-2:]:
            items.append(f"- ch{int(p.get('chapter_n', 0)):03d}: {str(p.get('overall',''))[:200]}")
        prev_block = "[직전 회차 줄거리 — 흐름이 끊기면 안 됨]\n" + "\n".join(items) + "\n\n"

    role_hint = (
        "이 막의 첫 화 — 막을 여는 인상적 사건/장면."
        if is_first else (
            "이 막의 마지막 화 — 막 climax를 정확히 친다." if is_last else
            "막 흐름 안에서 한 걸음 전진. 직전 화에서 자연스럽게 이어진다."
        )
    )

    return (
        f"[메타 작가 — 3단계: 단일 화 줄거리 (ch{chapter_n:03d})]\n\n"
        f"{TONE_RULES}\n"
        "[컨셉]\n"
        f"{_format_concept_block(concept)}\n"
        "[엔딩 + 3막 골격 — 변경 절대 금지]\n"
        f"{_format_ending_block(ending)}\n\n"
        f"{prev_block}"
        "[과제]\n"
        f"{act.get('name', f'{act_no}막')}({start}화~{end}화) 중 **ch{chapter_n:03d}** 한 화의 overall만 생성.\n"
        f"- {role_hint}\n"
        "- overall 분량: **정확히 200~300자**. 짧으면 반려, 길면 잘라야 함.\n"
        "- 핵심 사건 1~2개 + 감정/긴장 변화 1개 + 다음 회로 넘기는 후크.\n"
        "- 인물 소개·등급/직업 설명 반복 금지. 새 사건·새 정보·새 갈등만.\n"
        "- 직전 화에서 일어난 일을 그대로 반복하지 말고, 거기서 한 걸음 전진.\n"
        f"- chapter_n={chapter_n}, act={act_no} 정확히 기입.\n\n"
        "[출력 — 단일 객체 JSON 스키마. 다른 텍스트 절대 금지.]"
    )


def build_plot_chapter_revise_prompt(
    chapter: dict, feedback: str,
    concept: dict, ending: dict,
    *, act_idx: int, work_id: str,
) -> str:
    """단일 화 재생성."""
    import json as _json
    acts = ending.get("acts", [])
    act = acts[act_idx]
    act_no = act_idx + 1
    cur = _json.dumps(chapter, ensure_ascii=False, indent=2)
    return (
        f"[메타 작가 — 3단계 재생성: 단일 화 (ch{int(chapter.get('chapter_n', 0)):03d})]\n\n"
        f"{TONE_RULES}\n"
        "[컨셉]\n"
        f"{_format_concept_block(concept)}\n"
        "[엔딩 + 3막 골격 — 변경 절대 금지]\n"
        f"{_format_ending_block(ending)}\n\n"
        "[기존 화 줄거리]\n"
        f"{cur}\n\n"
        "[검수자 피드백]\n"
        f"{feedback.strip()}\n\n"
        "[수정 지시]\n"
        f"- 피드백 반영해 ch{int(chapter.get('chapter_n', 0)):03d} 한 화만 다시 짠다.\n"
        f"- chapter_n과 act={act_no}는 그대로.\n"
        "- overall 200~300자.\n\n"
        "[출력 — 단일 객체 JSON 스키마. 다른 텍스트 절대 금지.]"
    )


def build_plot_act_revise_prompt(
    skeleton_act: list[dict], feedback: str,
    concept: dict, ending: dict,
    *, act_idx: int, work_id: str,
) -> str:
    """막 줄거리 재생성. 같은 막 회차 수 유지, 피드백 반영."""
    import json as _json
    acts = ending.get("acts", [])
    act = acts[act_idx]
    rng = act.get("range", [1, 1])
    start, end = int(rng[0]), int(rng[1])
    n_chapters = end - start + 1
    act_no = act_idx + 1

    cur = _json.dumps({"chapters": skeleton_act}, ensure_ascii=False, indent=2)

    return (
        f"[메타 작가 — 3단계 재생성: {act.get('name', f'{act_no}막')} 회차별 줄거리]\n\n"
        f"{TONE_RULES}\n"
        "[컨셉]\n"
        f"{_format_concept_block(concept)}\n"
        "[엔딩 + 3막 골격 — 변경 절대 금지]\n"
        f"{_format_ending_block(ending)}\n\n"
        "[기존 막 줄거리]\n"
        f"{cur}\n\n"
        "[검수자 피드백]\n"
        f"{feedback.strip()}\n\n"
        "[수정 지시]\n"
        f"- 피드백을 반영해 {act.get('name', f'{act_no}막')}({start}화~{end}화) 회차 줄거리를 다시 짠다.\n"
        f"- chapters 길이 정확히 {n_chapters}, chapter_n은 {start}부터 {end}까지 순서대로, act={act_no}.\n"
        "- 각 화 overall 200~300자. 인물 소개 반복 금지.\n"
        "- 막 마지막 화는 막 climax를 정확히 친다.\n\n"
        "[출력 — 위 JSON 스키마를 정확히. 다른 텍스트 절대 금지.]"
    )


# ---------------------------------------------------------------------------
# 4단계: 비트 확장 (overall → beats[3])
# ---------------------------------------------------------------------------

def build_beat_expand_prompt(
    concept: dict, ending: dict, chapter: dict, *, work_id: str,
) -> str:
    """단일 회차 overall(200~300자) → 비트 3개(intro/development/climax) 분할.

    회차 작가가 비트별 1,800자+ 본문을 쓸 수 있도록 디테일 지시 포함.
    """
    chapter_n = int(chapter.get("chapter_n", 1))
    act_no = int(chapter.get("act", 1))
    overall = str(chapter.get("overall", "")).strip()

    # 회차 위치 컨텍스트
    acts = ending.get("acts", []) or []
    is_first_of_work = chapter_n == 1
    is_last_of_work = chapter_n == int(concept.get("total_chapters", 100))
    is_act_first = any(int(a.get("range", [0, 0])[0]) == chapter_n for a in acts)
    is_act_last = any(int(a.get("range", [0, 0])[1]) == chapter_n for a in acts)
    pos_hint = (
        "이 화는 작품 1화 — 인물·세계관·주요 설정을 자연스럽게 도입한다."
        if is_first_of_work else
        "이 화는 작품 마지막 화 — 엔딩과 정확히 일치하게 마무리한다."
        if is_last_of_work else
        "이 화는 막 첫 화 — 막을 여는 인상적 사건/공간/감정 변화."
        if is_act_first else
        "이 화는 막 마지막 화 — 해당 막 climax를 정확히 친다."
        if is_act_last else
        "막 흐름 안에서 한 걸음 전진하는 회차."
    )

    return (
        f"[메타 작가 — 4단계: ch{chapter_n:03d} 비트 확장]\n\n"
        f"{TONE_RULES}\n"
        "[작품 컨셉]\n"
        f"{_format_concept_block(concept)}\n"
        "[엔딩 + 3막 골격 — 변경 절대 금지]\n"
        f"{_format_ending_block(ending)}\n\n"
        f"[해당 회차 줄거리 — ch{chapter_n:03d} (act{act_no})]\n"
        f"{overall}\n\n"
        "[과제]\n"
        f"이 회차 줄거리를 비트 3개로 분할한다. {pos_hint}\n"
        "- 비트 이름: intro / development / climax (이 순서, 정확히 3개)\n"
        "- 각 비트 instruction은 회차 작가가 본문 1,800자+ 를 쓸 수 있는 디테일한 지시 목록.\n"
        "- instruction 항목별 디테일:\n"
        "  · 핵심 사건 1~3개 (구체적·동작 단위)\n"
        "  · 등장 인물 + 첫 호명 (호칭표 따름)\n"
        "  · 시각·후각·청각·촉각 묘사 포인트\n"
        "  · 대사 1~3개 (실제 대사 톤 예시 포함)\n"
        "  · 마지막 줄 — 다음 비트로 넘기는 후크\n"
        "- 비트 간 흐름이 자연스럽게 이어진다 (intro 마지막 → development 시작).\n"
        "- climax는 다음 회차로 넘기는 강한 후크/클리프행어로 끝난다.\n"
        "- 인물 소개 반복 금지(이미 안다). 새 사건·새 정보·새 감정만.\n\n"
        "[학습 예시 — 톤·디테일 참고용]\n"
        '{"beats":['
        '{"name":"intro","instruction":"이 부분은 회차 시작. 분량 1,800자 이상.\\n'
        '- 주인공의 자조/일상 톤 1줄로 시작\\n'
        '- 핵심 공간 묘사 (시각 2 + 후각/청각 1)\\n'
        '- 첫 인물 등장 + 호칭(\\"이준 씨\\" 등)\\n'
        '- 짧은 대사 1~2개\\n'
        '- 마지막 줄: 다음 비트로 넘기는 미세한 위기 신호"},'
        '{"name":"development","instruction":"이 부분은 회차 중반. 분량 1,800자 이상.\\n'
        '- 핵심 사건 발생 (동작 단위 묘사)\\n'
        '- 통증/충격 등 신체 감각\\n'
        '- 내적 독백 1~2줄\\n'
        '- 새 정보 발견 (단서/메모/시스템 메시지)"},'
        '{"name":"climax","instruction":"이 부분은 회차 마지막. 분량 1,800자 이상.\\n'
        '- 결정적 장면 (시스템 창 등 핵심 연출)\\n'
        '- 감정 정점\\n'
        '- 마지막 문장: 다음 화로 넘기는 강한 후크/클리프행어"}'
        "]}\n\n"
        "[출력 — 위 JSON 스키마 정확히. beats 배열 길이 정확히 3. 다른 텍스트 절대 금지.]"
    )


# ---------------------------------------------------------------------------
# 5단계: 사전 자산 (world_bible / characters / naming_table / persona)
# ---------------------------------------------------------------------------

def _format_skeleton_summary(skeleton: list[dict], total: int) -> str:
    """plot_skeleton에서 핵심 화(첫/막경계/마지막)만 추출해 압축."""
    if not skeleton:
        return "(skeleton 없음)"
    chapters_by_n = {c["chapter_n"]: c for c in skeleton}
    samples = []
    for n in sorted({1, total // 3, total * 2 // 3, total}):
        if n in chapters_by_n:
            ch = chapters_by_n[n]
            samples.append(f"- ch{n:03d}: {ch.get('overall', '')[:200]}")
    return "\n".join(samples)


def build_world_bible_prompt(concept: dict, ending: dict, skeleton: list[dict], *, work_id: str) -> str:
    """세계관 markdown 생성. 단일 호출."""
    total = int(concept.get("total_chapters", 100))
    return (
        "[메타 작가 — 5단계: 세계관 (world_bible.md)]\n\n"
        f"{TONE_RULES}\n"
        "[작품 컨셉]\n"
        f"{_format_concept_block(concept)}\n"
        "[엔딩]\n"
        f"{_format_ending_block(ending)}\n\n"
        "[줄거리 핵심 회차]\n"
        f"{_format_skeleton_summary(skeleton, total)}\n\n"
        "[과제]\n"
        "작품의 세계관(world_bible.md) 본문을 markdown으로 생성. 회차 작가가 이 문서만 보고도 일관된 세계관을 유지할 수 있어야 한다.\n"
        "포함 섹션:\n"
        "## 세계관 개요 — 2~3줄 핵심 설정\n"
        "## 시스템/메커니즘 규칙 — 등급·각성·시스템 등 핵심 규칙 구체화\n"
        "## 공간/조직 — 주요 공간(학교·이계·길드 등), 조직(권력층·대립 세력)\n"
        "## 자원/경제 — 화폐, 거래, 무역 (해당 시)\n"
        "## 금기/제약 — 작중 금지된 행위·역설·페널티\n"
        "각 섹션 3~6줄. 너무 길지 않게. 회차 작가용 reference이지 해설서가 아니다.\n"
        "출력 JSON: {\"content\": \"<markdown 전체>\"}\n"
    )


def build_characters_prompt(concept: dict, ending: dict, skeleton: list[dict], *, work_id: str) -> str:
    """등장인물 정의 — JSON. 5~8명."""
    total = int(concept.get("total_chapters", 100))
    return (
        "[메타 작가 — 5단계: 등장인물 (characters)]\n\n"
        f"{TONE_RULES}\n"
        "[작품 컨셉]\n"
        f"{_format_concept_block(concept)}\n"
        "[엔딩]\n"
        f"{_format_ending_block(ending)}\n\n"
        "[줄거리 핵심 회차]\n"
        f"{_format_skeleton_summary(skeleton, total)}\n\n"
        "[과제]\n"
        "작품의 주조연 5~8명을 정의한다. 회차 작가는 이 정의를 헌법으로 삼아 본문을 쓴다.\n"
        "각 인물:\n"
        "- name: 한국 이름. 컨셉의 protagonist 포함.\n"
        "- role: '주인공'/'조력자'/'적대자'/'조연' 중 하나.\n"
        "- rank: 등급 (해당 시 — F~S, 없으면 빈 문자열)\n"
        "- job: 직업/소속\n"
        "- personality: 성격 1~2줄 (반대로 묘사하면 즉시 반려될 수준의 명확성)\n"
        "- appearance: 외모 1줄\n"
        "- background: 가족·과거 1~2줄\n"
        "- arc: 1막→2막→3막 변화 (1줄로 압축, 막별)\n"
        "최소 5명, 최대 8명. 컨셉의 protagonist는 반드시 포함.\n"
        "주인공 1명, 1차 조력자 1~2명, 적대자 1~2명, 조연 1~3명 권장.\n"
    )


def build_naming_table_prompt(characters: list[dict], *, work_id: str) -> str:
    """호칭표 — 인물 간 호명 정의."""
    chars_block = "\n".join(
        f"- {c.get('name','?')} ({c.get('role','')}, {c.get('personality','')[:40]})"
        for c in (characters or [])
    )
    return (
        "[메타 작가 — 5단계: 호칭표 (naming_table)]\n\n"
        f"{TONE_RULES}\n"
        "[등장인물]\n"
        f"{chars_block}\n\n"
        "[과제]\n"
        "인물 간 호칭(첫 호명) 쌍을 정의한다. 회차의 호칭 검수자가 이 표를 ground truth로 쓴다.\n"
        "각 쌍:\n"
        "- speaker: 화자 이름\n"
        "- listener: 청자 이름\n"
        "- address: 호칭 (예: '이준 씨', '회장님', '누나')\n"
        "- context: '기본/공석', '사석/친밀', '긴급/명령' 중 하나 (선택)\n"
        "주조연 모든 양방향 쌍을 포함 (n명이면 최소 n*(n-1)/2 쌍).\n"
    )


def build_persona_prompt(concept: dict, *, work_id: str, author_id: str) -> str:
    """작가 페르소나 — authors/{id}.yaml 파일 내용."""
    return (
        "[메타 작가 — 5단계: 작가 페르소나]\n\n"
        f"{TONE_RULES}\n"
        "[작품 컨셉]\n"
        f"{_format_concept_block(concept)}\n\n"
        "[과제]\n"
        f"이 작품을 쓸 AI 작가의 페르소나를 정의한다. id는 '{author_id}' 그대로.\n"
        "필드:\n"
        "- id: '" + author_id + "' (이 값 그대로)\n"
        "- name: 한국식 필명 (작품 톤에 어울리는)\n"
        "- genre: 작품 장르 (concept.genre 활용)\n"
        "- style: 시점/문장 길이/호흡 (1줄)\n"
        "- tone: 분위기/대상 독자/액션 묘사 톤 (1~2줄)\n"
        "- favorite_tropes: 즐겨 쓰는 장치 4~6개 (배열)\n"
        "- avoid: 절대 안 쓰는 묘사 3~5개 (배열)\n"
        "한국 웹소설 작가 톤. 'modern_fantasy_writer_01' 같은 기존 페르소나 톤 참고.\n"
    )
