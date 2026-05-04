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

    return (
        f"[세계관 요약]\n{ctx.world_bible.strip()[:300]}\n\n"
        f"[등장인물 요약 — 본문에 인물 소개/등급/직업 묘사 반복 금지]\n{characters_compressed}\n\n"
        f"[작품 전체 플롯]\n{ctx.plot_outline.strip()[:500]}\n"
        f"{theme_block}"
        f"{naming_block}"
        f"{summary_block}"
    )


def build_beat_prompt(persona, ctx, beat, prev_tail: str, beat_index: int, total_beats: int) -> str:
    persona_block = build_persona_block(persona)
    context_block = build_context_block(ctx)

    prev_block = ""
    if prev_tail:
        prev_block = f"\n[직전 비트 끝부분]\n{prev_tail}\n"

    chapter_overall = ctx.chapter_outline.overall.strip()

    return (
        f"{persona_block}\n"
        f"{context_block}\n"
        f"[1화 전체 의도]\n{chapter_overall}\n"
        f"{prev_block}\n"
        f"[현재 비트: {beat_index + 1}/{total_beats} — {beat.name}]\n"
        f"{beat.instruction.strip()}\n\n"
        f"[작성 지시 — 한국 웹소설 4대 룰]\n"
        f"\n"
        f"### 룰 1. 주어 반복 금지 + 문장 구조 다양화\n"
        f"- '강이준은/그는/이준은'이 모든 문장의 첫머리에 오는 보고서 패턴 절대 금지.\n"
        f"- 한국어는 주어 생략이 자연스럽다. 문맥상 명확하면 그냥 '~했다'로 시작.\n"
        f"- '~했다.' 평서문 종결을 연속 3번 이상 쓰지 마라.\n"
        f"- 단문(짧은 임팩트)과 장문(상황 묶음)을 섞어 리듬감.\n"
        f"\n"
        f"### 룰 2. Telling 금지, Showing 강제 (가장 중요)\n"
        f"- 감정/상태/긴장감을 직접 요약하지 마라.\n"
        f"- ❌ '그는 무서웠다.' / '그는 절망했다.' / '그는 익숙했다.' (텔링)\n"
        f"- ✅ '입안에서 비릿한 쇠 맛이 났다.' (공포의 쇼잉)\n"
        f"- ✅ '땀이 턱 끝을 타고 뚝뚝 떨어졌다.' (긴장감의 쇼잉)\n"
        f"- ✅ '이준은 덜덜 떨리는 손으로 단검을 움켜쥐었다.' (공포·결의의 쇼잉)\n"
        f"- 오감(시각·후각·청각·촉각·미각), 시선 처리, 호흡, 주변 환경 변화로 독자가 유추하게.\n"
        f"\n"
        f"### 룰 3. 시각적 포맷팅 (가독성)\n"
        f"- 대사는 반드시 한 줄 띄우고 큰따옴표 \"…\" 사용.\n"
        f"- 시스템 메시지/퀘스트는 대괄호 [...]로 분리. 굵은 효과 위해 본문과 빈 줄로 분리.\n"
        f"- 효과음은 '— 쿠구구궁!' / '— 스윽, 쿵.' 식으로 대시(—)로 구분.\n"
        f"- 절정/액션 직전엔 문단을 짧게 끊어 속도감.\n"
        f"\n"
        f"### 룰 4. 톤·클리셰 (다크 판타지 헌터물)\n"
        f"- 3인칭 제한적 작가 시점.\n"
        f"- 분위기: 무겁고 차갑게. 신파·미사여구 빼고 건조하면서 타격감 있게.\n"
        f"- 한국 웹소설 ‘만년 약자’ 클리셰 정공.\n"
        f"\n"
        f"### 톤 참고 (절대 내용을 복사하지 마라. 오직 문체·호흡만 참고)\n"
        f"```\n"
        f"1인칭 또는 3인칭 제한 시점. 건조하고 타격감 있는 문장. 신파·미사여구 없이 사실을 나열하되 감정은 행동과 대사에만 싣는다.\n"
        f"문장 길이는 25~40자 평균. 임팩트 구간에만 단문(15자 이하) 사용.\n"
        f"의미상 이어지는 행동·묘사는 ~서/~며/~고/~기에로 한 문장으로 묶는다.\n"
        f"```\n"
        f"**경고: 위 참고 텍스트의 내용(배낭, 짐꾼, 던전 등)을 절대 복사하지 마라. 반복 발견 시 즉시 불합격 처리한다.**\n"
        f"\n"
        f"### 호흡·문장 길이 룰\n"
        f"- 평균 25~40자. 평균 20자 미만은 글이 깨짐. 절대 단편 나열 금지.\n"
        f"- 의미상 이어지는 행동·감정·반응은 ~서/~며/~고/~기에로 한 문장 묶음.\n"
        f"- 단문(15자 이하)은 임팩트 위치에만 회차당 5~7회.\n"
        f"- **'짧은 문장' ≠ '단편 나열'. 한 호흡 = 한 문장**. 자잘하게 끊지 말고 의미상 이어지는 행동·묘사·상태는 한 문장으로 묶어라.\n"
        f"  · **평균 문장 길이 25~40자 권장**. 평균 20자 미만은 글이 깨짐.\n"
        f"  · **15자 이하 단문은 회차 전체에서 강조 시점 5~7회 이내**. 그 외엔 다 연결어미로 묶는다.\n"
        f"  · **15자 이하 단문 연속 2개 이상 금지**. 단문은 임팩트 1방 후 즉시 긴 문장으로.\n"
        f"  · 사용할 연결어미: ~서/~며/~고/~지만/~데/~으로/~기에/~면서/~다가 등.\n"
        f"  · 원인-결과·순차 행동·대조·동시 묘사·감정-반응이 있으면 한 문장으로 묶는다.\n"
        f"  · 짧은 단문은 강조·박력·클리프행어 직전·대사 직전 등 \"의도된 임팩트\" 위치에만.\n"
        f"\n"
        f"  ❌ 절대 나쁜 예 (자잘한 끊김 — 글 깨짐):\n"
        f"     '강이준은 짐을 끌었다. 5년이었다. 그랬다. 어깨가 무거웠다. 한숨이 났다. 길었다. 익숙했다.'\n"
        f"  ✅ 좋은 예 (한 호흡으로 묶음):\n"
        f"     '강이준은 만 5년째 같은 짐을 끌고 있었고, 어깨를 짓누르는 무게는 이미 익숙한 그의 일부가 되어 있었다. 길게 한숨이 새어 나왔다.'\n"
        f"\n"
        f"  ❌ 또 다른 나쁜 예:\n"
        f"     '세린의 눈빛은 차가웠다. 감정을 읽기 어려웠다. 그녀가 단검을 들었다. 손목이 움직였다. 빨랐다.'\n"
        f"  ✅ 좋은 예:\n"
        f"     '세린의 눈빛은 늘 그렇듯 차가워서 감정을 읽기 어려웠다. 그녀가 단검을 빼들자 손목이 빠르게 호선을 그렸다 — 어쌔신의 본능이었다.'\n"
        f"\n"
        f"  · 한 문단은 길이 다른 문장이 섞여야 한다 (긴 문장 2~3개 + 짧은 임팩트 문장 0~1개).\n"
        f"- **인물 호명 (한국 웹소설 표준 — 매우 중요)**: 독자는 이미 주인공·주조연을 안다. 풀네임 난발 금지.\n"
        f"  · **주인공 풀네임(강이준)은 회차 전체에서 최대 3~5회만**. 비트 시작·강조 시점·클리프행어 등 꼭 필요한 곳에만.\n"
        f"  · 90% 이상은 '그' 또는 **성 떼고 짧은 이름**('이준'). 대명사가 어색할 때는 주어 생략(주어 없는 문장)도 자연스러움.\n"
        f"  · **성 떼는 호명은 한국 웹소설 표준**: 강이준→이준 / 박세린→세린 / 한도혁→도혁. 거리감 좁히고 가독성 살림.\n"
        f"  · 박세린·다른 조연도 동일 — 풀네임 회차당 3~5회 이내, 나머지는 '세린' 또는 '그녀'.\n"
        f"  · 한 문단 안에 같은 풀네임 2회 이상 등장 금지.\n"
        f"  · 5문장 연속 같은 풀네임만 등장 금지.\n"
        f"  · 예시 (좋음): \"이준은 짐을 끌었다. 어깨가 무거웠다. 그는 한숨을 쉬었다. 발걸음이 느려졌다.\"\n"
        f"  · 예시 (나쁨): \"강이준은 짐을 끌었다. 강이준의 어깨가 무거웠다. 강이준은 한숨을 쉬었다. 강이준의 발걸음이 느려졌다.\"\n"
        f"  · **단, 호칭표(naming_table.md)에 정의된 인물 간 호칭은 대사에서 그대로 사용해야 한다**.\n"
        f"    예: 박세린이 강이준에게 말하는 대사는 호칭표대로 \"이준 씨, …\" 형태로 시작 (회차에 박세린 대사가 있다면 최소 1회).\n"
        f"  · **서술 문장에서 \"X는 Y를 'Z'라 불렀다\" 같은 메타 호칭 묘사는 쓰지 마라**. 호칭은 대사로 직접 보여줘라. 메타 묘사를 쓰면 대사의 호칭과 일치시켜야 하므로 부담만 늘어난다.\n"
        f"- 본문만 출력. 해설·메타 코멘트 금지.\n"
        f"- 분량 1,800자 이상.\n"
        f"\n"
        f"### 캐릭터 소개 반복 절대 금지 (매우 중요)\n"
        f"- 독자는 이미 인물을 알고 있다. 'F급 헌터', 'B급 어세신', 'S급', '짐꾼' 같은 등급·직업 설명을 본문에 다시 쓰지 마라.\n"
        f"- 인물의 능력·과거·외모·특성을 서술로 설명하는 것 금지. 행동과 대사로만 보여줘라.\n"
        f"- ❌ '그는 F급 헌터였다. 5년간 짐꾼으로 살았다.' (이미 독자가 아는 정보 재설명)\n"
        f"- ✅ '이준은 던전 입구에서 짐을 내려놓았다.' (행동만으로 충분, 등급 묘사 불필요)\n"
        f"- ❌ '박세린은 B급 어세신으로 빠른 검술을 자랑했다.' (직업 설명 반복)\n"
        f"- ✅ '세린의 단검이 번뜩였다. 손목이 움직이기도 전에 검격이 날아왔다.' (능력을 행동으로 보여줌)\n"
        f"- 이 룰을 어기면 즉시 불합격."
    )


def build_revise_prompt(persona, ctx, draft: str, feedback: str) -> str:
    persona_block = build_persona_block(persona)
    context_block = build_context_block(ctx)
    return (
        f"{persona_block}\n"
        f"{context_block}\n"
        f"[기존 본문]\n{draft.strip()}\n\n"
        f"[검수자 피드백]\n{feedback.strip()}\n\n"
        f"[수정 지시]\n"
        f"- 피드백을 반영해 본문 전체를 다시 작성.\n"
        f"- 페르소나/세계관/캐릭터 일관성은 유지.\n"
        f"- 한국 웹소설 스타일 유지. 본문만 출력."
    )


def build_polish_prompt(persona, body: str) -> str:
    """완성된 본문의 호흡만 다듬는 정제 프롬프트. 의미·이름·플롯 변경 금지."""
    return (
        f"[작가 페르소나]\n"
        f"필명: {persona.name}\n"
        f"스타일: 한국 웹소설 다크 판타지 — 평균 문장 25~40자, 건조하고 타격감 있는 문체\n\n"
        f"[정제 지시 — 한국 웹소설 4대 룰로 다듬는다]\n"
        f"아래 본문을 다음 4가지 룰로 정제. 의미·이름·플롯·대사·시스템창은 100% 보존.\n\n"
        f"룰 1. 주어 반복 제거: '강이준은/그는'이 모든 문장 첫머리에 오는 부분, 주어 생략 또는 어미 연결로 통합.\n"
        f"룰 2. Telling 제거: '그는 무서웠다/익숙했다/절망했다' 같은 직접 요약은 오감 묘사로 변환 (땀·떨림·시선·호흡 등).\n"
        f"룰 3. 시각 포맷: 대사 줄바꿈 + 큰따옴표, 시스템 [...] 분리, 효과음 '—'로.\n"
        f"룰 4. 호흡: 자잘한 단문 ~서/~며/~고로 묶기. 평균 25~40자.\n\n"
        f"[절대 변경 금지]\n"
        f"- 인물 이름·등급(F급/B급/S급 등)·직업·관계\n"
        f"- 모든 대사 (큰따옴표 안 텍스트는 한 글자도 변경 X)\n"
        f"- 호칭 ('이준 씨' 등)\n"
        f"- 사건·플롯·장면 순서·시스템 메시지·스탯창\n"
        f"- AI 배지(`> 🤖`) 와 제목(`# N화. ...`) 줄은 그대로 유지\n"
        f"- 분량은 ±10% 이내\n\n"
        f"[허용된 작업만]\n"
        f"- 단문→어미연결 (한 호흡으로 묶기)\n"
        f"- '그는 X했다' → 오감·동작 묘사로 교체\n"
        f"- 어미 변환 (~다. → ~며, ~고, ~서)\n"
        f"- 동일 행동·상태·감정이 연속 짧게 묘사되면 한 문장으로 통합\n\n"
        f"❌ 원본: '강이준은 짐을 끌었다. 5년이었다. 그랬다. 어깨가 무거웠다. 익숙했다.'\n"
        f"✅ 정제: '강이준은 5년째 같은 짐을 끌어 어깨를 짓누르는 무게는 이미 익숙했다.'\n\n"
        f"[입력 본문]\n"
        f"{body}\n\n"
        f"[정제된 본문 — 본문만 출력. 해설·메타코멘트 절대 금지.]"
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
