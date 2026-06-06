"""작가 프롬프트 빌더."""
from __future__ import annotations


def build_persona_block(persona) -> str:
    tropes = ", ".join(persona.favorite_tropes) if persona.favorite_tropes else "—"
    avoid = ", ".join(persona.avoid) if persona.avoid else "—"
    samples = ""
    for i, p in enumerate(persona.sample_passages[:2]):
        samples += f"\n[문체 예시 {i + 1}]\n{p.strip()}\n"
    return (
        f"[작가 페르소나]\n"
        f"필명: {persona.name}\n"
        f"문체: {persona.style}\n"
        f"톤: {persona.tone}\n"
        f"즐겨 쓰는 클리셰: {tropes}\n"
        f"피해야 할 것: {avoid}\n"
        f"{samples}"
    )


def _compress_characters(characters_text: str) -> str:
    """characters.md를 한 줄 요약으로 압축 — 본문에 캐릭터 소개 반복 방지."""
    lines = [l.strip() for l in characters_text.strip().splitlines() if l.strip()]
    compressed = []
    for line in lines:
        # 헤딩(#, ##)은 이름만 추출
        if line.startswith("#"):
            compressed.append(line)
        # 이미 한 줄인 항목은 그대로
        elif len(line) < 80 and ":" in line:
            compressed.append(line)
        # 긴 설명은 첫 문장만
        elif line and not line.startswith("-") and not line.startswith("*"):
            first_sentence = line.split(".")[0].split("。")[0]
            compressed.append(first_sentence + ("." if not first_sentence.endswith("。") else ""))
    # 빈 줄 제거, 2줄 이상 유지
    result = "\n".join(l for l in compressed if l)
    return result if len(result) < 500 else characters_text[:500] + "\n... (생략)"


def build_context_block(ctx) -> str:
    summary_block = ""
    if ctx.recent_summaries:
        summary_block = "\n[직전 회차 요약]\n"
        for i, s in enumerate(ctx.recent_summaries):
            summary_block += f"\n--- 회차 {ctx.current_chapter_n - len(ctx.recent_summaries) + i} ---\n{s}\n"

    theme_block = f"\n[작품 테마/약속 — 절대 어기지 말 것]\n{ctx.theme.strip()}\n" if ctx.theme else ""
    naming_block = f"\n[호칭표 — 인물 호칭은 반드시 이 표대로]\n{ctx.naming_table.strip()}\n" if ctx.naming_table else ""

    characters_compressed = _compress_characters(ctx.characters)

    wiki_block = ""
    wc = getattr(ctx, "wiki_context", "")
    if wc:
        wiki_block = f"\n{wc}\n"

    return (
        f"[세계관 요약]\n{ctx.world_bible.strip()[:300]}\n\n"
        f"[등장인물 요약 — 본문에 인물 소개/등급/직업 묘사 반복 금지]\n{characters_compressed}\n\n"
        f"[작품 전체 플롯]\n{ctx.plot_outline.strip()[:500]}\n"
        f"{theme_block}"
        f"{naming_block}"
        f"{summary_block}"
        f"{wiki_block}"
    )


def _get_pronoun(char: dict) -> str:
    """캐릭터 성별에 맞는 대명사 반환."""
    gender = str(char.get("gender", "")).strip().lower()
    if gender == "female":
        return "그녀"
    if gender == "male":
        return "그"
    return "그"


def _format_main_characters(ctx) -> str:
    """ctx.main_characters를 프롬프트용 호명 가이드로 직렬화."""
    chars = list(getattr(ctx, "main_characters", []) or [])
    if not chars:
        return "[현재 작품 주인공 정보 없음 — meta.json의 main_characters 누락]"
    lines = ["[현재 작품 주조연 호명 — 본문에서 반드시 이 이름 사용]"]
    for i, c in enumerate(chars):
        name = c.get("name", "")
        short = c.get("short", "")
        pronoun = _get_pronoun(c)
        role = "주인공" if i == 0 else "조연"
        if short:
            lines.append(f"- {role}: 풀네임 '{name}', 짧은 이름 '{short}', 대명사 '{pronoun}'")
        else:
            lines.append(f"- {role}: '{name}', 대명사 '{pronoun}' — 회차당 풀네임 5회 이내, 나머지는 대명사·주어 생략")
    lines.append("⚠️ 학습 예시에 등장하는 타 작품 인물명은 본 작품 본문에 절대 등장시키지 말고, 위 호명만 사용.")
    return "\n".join(lines)


def _get_genre_tone_block(persona, ctx) -> str:
    """작품 장르·톤에 맞는 룰 4 + 룰 6 블록을 동적 생성."""
    genre = getattr(persona, "genre", "") or ""
    tone = getattr(persona, "tone", "") or ""

    # 장르별 톤 + 금지어 + 갈등 스케일
    if "슬로우" in genre or "무역" in genre or "라이프" in genre:
        return (
            "### 룰 4. 톤·장르 — 슬로우라이프 + 무역\n"
            "- 3인칭 제한 시점.\n"
            "- 분위기: 차분하고 관찰적. 일상 속 긴장감. 감정은 행동과 대사에 싣는다.\n"
            "- 무역·거래·협상 장면은 긴장감 있게. 일상 장면은 여유롭게.\n"
            "- 신파·미사여구 금지. 사실을 건조하게 나열하되 타격감은 살린다.\n\n"
            "### 룰 6. 장르 약속 — 갈등은 항상 '일상 스케일'\n"
            "- 이 작품은 슬로우라이프 + 무역물이다. 갈등의 크기는 늘 **돈·인간관계·일상 속 발견**이어야 한다.\n"
            "- ❌ '세계를 재구성할 수 있는 존재가 되었다' (오버킬 — 장르 약속 위반)\n"
            "- ✅ '이거 팔면 얼마받을 수 있지? 한 달 치 식비는 벌겠네' (무역 스케일)\n"
            "- 클리프행어도 작아야 한다: '다음 마을에서도 이런 돌이 있을까?' 정도.\n"
            "- 주인공은 '관찰자'가 아니라 **'계산하는 장사꾼'**이어야 한다. 발견하면 바로 가격을 매긴다.\n\n"
            "### 룰 7. 금지어 — 이 단어들이 나오면 AI 냄새가 난다\n"
            "- 시스템창([...] 안)을 제외하고, 서술에서 다음 단어 사용 금지:\n"
            "  존재론적, 에너지 흐름, 시스템적, 이질적, 물리적 법칙, 차원의, 근원적\n"
            "  계산했다, 분석했다, 인식했다, 깨달았다, 직감했다 — 행동으로 보여줘라\n"
            "- 키워드로 캐릭터를 설명하지 마라. 행동으로 보여라:\n"
            "  ❌ '하린은 그 무게를 계산했다' / '하린은 이것이 가짜라는 것을 깨달았다'\n"
            "  ✅ '빵이 50전인데 동전 두 개는 100전. 거스름이 100전이다' / '풀빛이 손끝에서 미세하게 떨렸다. 다른 풀들은 그렇지 않았다'\n"
            "- 특별함을 설명할 때 추상 용어 대신 **구체적 감각**을 써라:\n"
            "  ❌ '존재론적 무게를 지니고 있었다'\n"
            "  ✅ '손에 쥔 돌이 미세하게 따뜻했다. 주변 돌들은 차가웠는데, 이것만 체온처럼'\n"
        )
    elif "헌터" in genre or "던전" in genre or "다크" in genre:
        return (
            "### 룰 4. 톤·장르 — 헌터/액션\n"
            "- 3인칭 제한 시점.\n"
            "- 분위기: 무겁고 차갑게. 신파·미사여구 빼고 건조하면서 타격감 있게.\n"
            "- 한국 웹소설 '만년 약자' 클리셰 정공.\n\n"
            "### 룰 6. 장르 약속 — 갈등은 '생존 스케일'\n"
            "- 갈등의 크기는 등급·목숨·동료의 안전이어야 한다.\n"
            "- ❌ '세계를 구원할 운명을 가졌다' (1화에 오버킬)\n"
            "- ✅ '오늘 던전에서 살아남으면 그만큼 벌 수 있다' (생존+돈 스케일)\n\n"
            "### 룰 7. 금지어\n"
            "- 시스템창 제외 서술에서 금지: 존재론적, 에너지 흐름, 근원적, 차원의\n"
            "- 구체적 감각으로 대체.\n"
        )
    else:
        return (
            "### 룰 4. 톤·장르\n"
            "- 3인칭 제한 시점.\n"
            "- 페르소나 톤을 따른다: " + (tone[:100] if tone else "건조하고 타격감 있는 문체") + "\n"
            "- 신파·미사여구 금지.\n\n"
            "### 룰 6. 장르 약속\n"
            "- 갈등은 장르에 맞는 스케일이어야 한다. 1화에서 세계를 구원하지 마라.\n\n"
            "### 룰 7. 금지어\n"
            "- 서술에서 금지: 존재론적, 에너지 흐름, 근원적. 구체적 감각으로 대체.\n"
        )


def _get_example_names(ctx) -> tuple:
    """작품 주인공 기반 예시 이름 반환: (full, short, pronoun)."""
    if ctx is not None:
        chars = list(getattr(ctx, "main_characters", []) or [])
        if chars:
            return (
                chars[0].get("name", "주인공"),
                chars[0].get("short", "그"),
                _get_pronoun(chars[0]),
            )
    return "주인공", "그", "그"


def build_beat_prompt(persona, ctx, beat, prev_tail: str, beat_index: int, total_beats: int) -> str:
    persona_block = build_persona_block(persona)
    context_block = build_context_block(ctx)
    main_block = _format_main_characters(ctx)
    genre_tone_block = _get_genre_tone_block(persona, ctx)
    proto_full, proto_short, proto_pronoun = _get_example_names(ctx)

    prev_block = ""
    if prev_tail:
        prev_block = (
            f"\n[직전 비트 전체 — 이미 본문에 작성된 부분, 절대 다시 쓰지 마라]\n{prev_tail}\n"
            f"\n⚠️ 위는 이미 회차에 들어간 본문이다. 위에서 이미 묘사된 사건·장면·대사·장소·인물·물건을 이 비트에서 다시 쓰지 마라.\n"
            f"- 같은 사건을 두 번 묘사하면 회차가 깨진다.\n"
            f"- 이 비트는 위 본문이 끝난 시점에서 **이어지는 새로운 사건**만 다룬다.\n"
        )

    chapter_overall = ctx.chapter_outline.overall.strip()

    # 오프닝 훅 — 첫 비트에만 삽입
    hook_block = ""
    if beat_index == 0:
        hook_block = (
            f"### 룰 0. 오프닝 훅 — 이 비트에서만 적용\n"
            f"**첫 3문장에서 독자를 잡아라.** 배경 설명으로 시작하지 마라.\n"
            f"- 첫 문장에 캐릭터의 문제·갈등·궁금함 중 하나를 걸어라.\n"
            f"- ❌ '햇살이 흙먼지를 흩뿌렸다. 낯선 곳의 아침이었다.' (배경 설명 — 관심 없음)\n"
            f"- ✅ '빵값이 없었다. 주머니를 뒤져 나온 건 동전 두 개와 구멍 난 껌 하나.' (문제 제시)\n"
            f"- ✅ '셋째 날, {proto_short}은 이 마을이 가짜라는 것을 알았다.' (긴장감 즉시 주입)\n\n"
        )

    return (
        f"{persona_block}\n"
        f"{main_block}\n\n"
        f"{context_block}\n"
        f"[1화 전체 의도]\n{chapter_overall}\n"
        f"{prev_block}\n"
        f"[현재 비트: {beat_index + 1}/{total_beats} — {beat.name}]\n"
        f"{beat.instruction.strip()}\n\n"
        f"[비트 사건 범위 룰]\n"
        f"- instruction에 적힌 사건만 묘사.\n"
        f"- 이미 묘사된 사건·다루지 말 것은 절대 쓰지 마라.\n"
        f"- 회상·요약으로 우회도 금지.\n\n"
        f"[캐릭터 목소리 — {proto_short}는 '관찰자'가 아니라 '사람'이다]\n"
        f"- {proto_short}은 감정이 없는 게 아니라 감정을 드러내지 않을 뿐이다.\n"
        f"- 놀라면 입을 다물고, 기쁘면 눈이 가늘어지고, 불편하면 시선을 돌린다.\n"
        f"- {proto_short}의 반응은 항상 **행동**으로 나타난다. 절대 '{proto_pronoun}는 깨달았다/인식했다/직감했다'로 요약하지 마라.\n"
        f"- 대사에서 {proto_short}의 개성이 나와야 한다: 건조한 유머, 계산적인 말투, 필요 이상의 말은 하지 않는 습관.\n\n"
        f"[작성 지시 — 한국 웹소설 7대 룰]\n"
        f"\n"
        f"{hook_block}"
        f"\n"
        f"### 룰 1. 대사 우선 — 이것이 최우선\n"
        f"- **비트당 대사 최소 3개**. 대사 없는 비트는 불합격.\n"
        f"- 대사로 캐릭터 성격을 보여줘라. 침묵도 \"…\"로 표현.\n"
        f"- 대사는 한 줄 띄우고 큰따옴표 \"…\" 사용.\n"
        f"- 혼잣말도 대사 포맷(따옴표) 사용. 서술에 섞지 마라.\n"
        f"- ✅ '하린은 광물을 뒤집으며 말했다.\\n\"이건 종류가 다르다.\"\\n손끝에서 진동이 퍼졌다.'\n"
        f"- ❌ '하린은 이것이 종류가 다르다는 것을 알 수 있었다.' (대사 없이 텔링)\n"
        f"\n"
        f"### 룰 2. Showing — 감정·상태는 행동·오감으로\n"
        f"- 감정·상태·긴장감을 직접 요약하지 마라. 행동·오감으로 보여줘라.\n"
        f"- ❌ '{proto_pronoun}는 무서웠다.' / '{proto_pronoun}는 절망했다.' / '{proto_pronoun}는 익숙했다.'\n"
        f"- ✅ '입안에서 비릿한 쇠 맛이 났다.' / '손끝이 떨려 광물을 놓칠 뻔했다.'\n"
        f"- 오감(시각·후각·청각·촉각·미각), 시선, 호흡, 주변 변화로 독자가 유추하게.\n"
        f"\n"
        f"### 룰 3. 주어 회전 — 이 룰을 어기면 회차가 불합격\n"
        f"**절대 같은 주어로 3문장 연속 시작하지 마라.**\n\n"
        f"주어 회전 주기 (이 순서대로 순환):\n"
        f"  1) '{proto_short}은/는' (짧은 이름)\n"
        f"  2) (주어 생략) ~했다 / ~었다\n"
        f"  3) '{proto_pronoun}는/가/의' (대명사)\n"
        f"  4) (주어 생략) ~며/~고/~서 이었다\n"
        f"  5) 다시 1)부터 반복\n\n"
        f"- 한국어는 주어 생략이 가장 자연스럽다. 문맥상 명확하면 무조건 생략.\n"
        f"- 의미상 이어지는 행동·감정은 ~서/~며/~고/~기에로 한 문장으로 묶어라.\n"
        f"- 평균 25~40자. 단문(15자 이하)은 임팩트 위치에만 회차당 5~7회.\n"
        f"- 단문 연속 2개 이상 금지. 임팩트 1방 후 긴 문장으로.\n"
        f"\n"
        f"  ❌ 나쁜 예 (보고서 패턴 — 절대 금지):\n"
        f"  '{proto_short}은 짐을 끌었다. {proto_short}은 땀을 닦았다. {proto_short}은 한숨을 쉬었다. {proto_short}은 앞으로 나아갔다.'\n"
        f"  ✅ 좋은 예 (회전 + 생략 + 어미 연결):\n"
        f"  '{proto_short}은 오래도록 같은 짐을 끌어왔고, 어깨를 짓누르는 무게는 이미 익숙한 일부가 되어 있었다. 길게 한숨이 새어 나왔다. {proto_pronoun}의 발걸음은 멈추지 않았다.'\n"
        f"\n"
        f"### 룰 4. 시각 포맷\n"
        f"- 대사: 줄바꿈 + 큰따옴표 \"…\"\n"
        f"- 시스템 메시지: 대괄호 [...] 본문과 빈 줄 분리.\n"
        f"- 효과음: '— 쿠구구궁!' 대시(—) 구분.\n"
        f"- 절정 직전 문단 짧게 끊어 속도감.\n"
        f"\n"
        f"{genre_tone_block}\n"
        f"\n"
        f"### 룰 5. 인물 호명 + 캐릭터 소개 금지\n"
        f"- 독자는 이미 인물을 안다. 등급·직업·능력 설명 본문에 쓰지 마라.\n"
        f"- **{proto_full}(풀네임)은 회차당 최대 5회**. 나머지는 '{proto_short}' 또는 대명사 '{proto_pronoun}' ·주어 생략.\n"
        f"- 한 문단 안에 '{proto_short}' 3회 이상 금지 — 두 번째부터는 '{proto_pronoun}' 또는 생략.\n"
        f"- 호칭표(naming_table)에 정의된 호칭은 대사에서 그대로 사용.\n"
        f"- ❌ '그는 무역가였다. 3년간 이계를 오갔다.' (독자가 아는 정보 재설명)\n"
        f"- ✅ '{proto_short}는 광물을 손에 쥐고 무게를 가늠했다.' (행동만으로 충분)\n"
        f"\n"
        f"[분량] 3,000자 이상. 본문만 출력. 해설·메타 코멘트 금지."
    )


def build_revise_prompt(persona, ctx, draft: str, feedback: str) -> str:
    persona_block = build_persona_block(persona)
    context_block = build_context_block(ctx)
    main_block = _format_main_characters(ctx)
    return (
        f"{persona_block}\n"
        f"{main_block}\n\n"
        f"{context_block}\n"
        f"[기존 본문]\n{draft.strip()}\n\n"
        f"[검수자 피드백]\n{feedback.strip()}\n\n"
        f"[수정 지시]\n"
        f"- 피드백을 반영해 본문 전체를 다시 작성.\n"
        f"- 페르소나/세계관/캐릭터 일관성은 유지.\n"
        f"- 한국 웹소설 스타일 유지. 본문만 출력."
    )


def build_polish_prompt(persona, body: str, ctx=None) -> str:
    """완성된 본문의 호흡만 다듬는 정제 프롬프트. 의미·이름·플롯 변경 금지."""
    main_block = _format_main_characters(ctx) if ctx is not None else ""
    proto_full, proto_short, proto_pronoun = _get_example_names(ctx) if ctx is not None else ("주인공", "그", "그")
    return (
        f"[작가 페르소나]\n"
        f"필명: {persona.name}\n"
        f"스타일: {getattr(persona, 'style', '한국 웹소설 — 평균 문장 25~40자')}\n\n"
        f"{main_block}\n\n"
        f"[정제 지시 — 아래 룰로 다듬는다]\n"
        f"의미·이름·플롯·대사·시스템창은 100% 보존.\n\n"
        f"룰 1. 대사 확인: 대사가 부족하면 행동·내면 묘사를 대사로 전환.\n"
        f"룰 2. 주어 회전: 같은 주어 3문장 연속 → 2번째를 '{proto_pronoun}'로, 3번째를 생략.\n"
        f"  '{proto_short}은 A했다. {proto_short}은 B했다. {proto_short}은 C했다.'\n"
        f"  → '{proto_short}은 A했다. {proto_pronoun}는 B했다. C했다.'\n"
        f"룰 3. Telling → Showing: '무서웠다/익숙했다/절망했다' 직접 요약은 오감 묘사로 변환.\n"
        f"룰 4. 시각 포맷: 대사 줄바꿈 + 큰따옴표, 시스템 [...] 분리, 효과음 '—'로.\n"
        f"룰 5. 호흡: 자잘한 단문 ~서/~며/~고로 묶기. 평균 25~40자.\n\n"
        f"[절대 변경 금지]\n"
        f"- 인물 이름·관계\n"
        f"- 모든 대사 (큰따옴표 안 텍스트 한 글자도 변경 X)\n"
        f"- 사건·플롯·장면 순서·시스템 메시지\n"
        f"- AI 배지(`> 🤖`) 와 제목(`# N화. ...`) 줄 유지\n"
        f"- 분량 ±10% 이내\n\n"
        f"[입력 본문]\n"
        f"{body}\n\n"
        f"[정제된 본문 — 본문만 출력. 해설·메타코멘트 절대 금지.]"
    )


def build_rep_polish_prompt(draft: str, feedback: str, ctx=None) -> str:
    """반복 패턴 정제 프롬프트 — 2B 모델용 단순·기계적 지시."""
    main_block = _format_main_characters(ctx) if ctx is not None else ""
    proto_full, proto_short, proto_pronoun = _get_example_names(ctx) if ctx is not None else ("주인공", "그", "그")
    forced_block = ""
    if proto_full and proto_short and proto_full != "주인공":
        forced_block = (
            f"\n### ⚠️ 강제 교체 룰 — 반드시 실행\n"
            f"- '{proto_full}'(풀네임)이 5회 초과 → 6번째부터 모두 '{proto_short}' 또는 '{proto_pronoun}'로 교체.\n"
            f"- 한 문단 안에 '{proto_short}' 3회 이상 → 4번째부터 모두 '{proto_pronoun}' 또는 주어 생략.\n"
            f"  예: '{proto_short}은 걸었다. {proto_short}은 봤다. {proto_short}은 멈췄다.'\n"
            f"  →  '{proto_short}은 걸었다. {proto_pronoun}는 주변을 둘러봤다. 발걸음이 멈췄다.'\n\n"
        )
    return (
        "[반복 정제 — 아래 지시를 문장별로 그대로 실행]\n\n"
        f"{main_block}\n"
        f"{forced_block}"
        f"[검수자 피드백]\n{feedback.strip()}\n\n"
        "[보존 규칙] 사건·플롯·대사·시스템 메시지는 한 글자도 바꾸지 마라.\n\n"
        "[실행 순서 — 문장 하나하나 검사]\n"
        "1. 같은 주어가 3문장 연속이면 → 2번째 주어를 대명사로, 3번째 주어를 생략.\n"
        f"2. '{proto_short}은/는/이/가'가 한 문단에 3회 이상 → 뒤의 것을 '{proto_pronoun}는/가' 또는 생략로 교체.\n"
        f"3. 같은 행동 동사 3회 이상 → 유의어로 교체 (바라보았다→응시했다/시선을 주었다).\n"
        "4. 단문(15자 이하)이 연속 2개 → ~서/~며/~고로 한 문장으로 합쳐라.\n\n"
        f"[치환 예시]\n"
        f"  변경 전: '{proto_short}은 돌을 집었다. {proto_short}은 돌을 돌렸다. {proto_short}은 빛을 봤다.'\n"
        f"  변경 후: '{proto_short}은 돌을 집어 손바닥 위에서 천천히 돌렸다. {proto_pronoun}의 눈에 푸른빛이 비쳤다.'\n\n"
        "[입력 본문]\n"
        f"{draft.strip()}\n\n"
        "[정제된 본문 — 본문만 출력. 해설·메타코멘트 금지.]"
    )


def build_summary_prompt(persona, ctx, chapter_text: str) -> str:
    return (
        f"[작가]\n{persona.name}\n\n"
        f"[방금 쓴 회차 본문]\n{chapter_text.strip()}\n\n"
        f"[지시]\n"
        f"이 회차의 핵심을 5-8줄 요약. 다음 회차 작가가 참고할 사실들.\n"
        f"- 등장 인물 / 일어난 사건 / 새로운 정보 / 미해결 떡밥\n"
        f"- 본문 인용 금지. 사실 위주."
    )
