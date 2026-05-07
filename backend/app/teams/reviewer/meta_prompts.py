"""메타 파이프라인 검수자 프롬프트 — ending_lock / outline_consistency.

기존 prompts.py의 REVIEW_SCHEMA를 그대로 재사용. 출력은 JSON 한 덩어리:
{"판정","점수","이유","수정가이드"}
톤·금지 규칙은 메모리 규칙(헌터물·시스템물·100화·게임표준어)을 그대로 반영.
"""
from __future__ import annotations

import json


# ---------------------------------------------------------------------------
# 공통 — 게임표준어 규칙 블록 (모든 메타 검수 프롬프트 끝부분에 붙임)
# ---------------------------------------------------------------------------

_KOREAN_LOC_RULE = (
    "[한글화 규칙 — 어기면 즉시 반려]\n"
    "- 게임표준어(영문 그대로 OK): 마나, 길드, 던전, 헌터, 보스, 레이드, 파티\n"
    "- 한글로만 적어야 함: 어쌔신(X) → 암살자/그림자단검(O), 탱커(X) → 방벽/방어수(O),\n"
    "  스탯 약어(STR/DEX/INT 등 X) → 근력/민첩/지능(O)\n"
    "- 시스템 메시지/창은 한글 표기. 영문 약어가 본문/줄거리에 노출되면 반려.\n\n"
)


_OUTPUT_HINT = (
    "[출력 — 다음 JSON 스키마를 정확히 지켜라. 다른 텍스트 절대 금지.]\n"
    '{"판정": "통과" 또는 "반려", "점수": 0~10 정수, "이유": "한 문장 — 인용 비교 포함", '
    '"수정가이드": "반려 시 가이드, 통과면 빈 문자열"}'
)


# ---------------------------------------------------------------------------
# 1) EndingLockReviewer.review_ending — concept ↔ ending 정합
# ---------------------------------------------------------------------------

_ENDING_LOCK_INSTRUCTION = """[검수 대상]
컨셉(concept)과 엔딩(ending: 1줄 엔딩 + 3막 골격)이 일관된지 본다.
산문 평가·문장력·재미는 보지 마라. 컨셉과 엔딩의 모순만 본다.

[검사 항목]
1. ending["summary"] (1줄 엔딩) 이 concept["logline"]/keywords/protagonist와 모순 없는가
   - 장르(헌터물/현대판타지/시스템물 등)가 일치하는가
   - protagonist 이름이 엔딩에 등장하는가 (또는 명백히 그를 지칭하는가)
   - forbidden 요소(성적 묘사/실명 거론 등)가 엔딩에 들어가 있으면 즉시 반려
2. ending["acts"] 3막의 range가 [1, total_chapters]를 빠짐없이 덮는가
   - 예: total=100 → [1,33], [34,67], [68,100] 식. 끊기거나 겹치면 반려.
   - 막 개수가 정확히 3개여야 함.
3. 각 막의 climax가 점점 격해지는가
   - 1막 climax < 2막 climax < 3막 climax 의 강도 흐름.
   - 3막 climax가 가장 격해야 하며, 1줄 엔딩(ending["summary"])과 직결되어야 함.

[필수 출력 규칙 — "이유" 필드에 인용 비교 강제]
"이유"에는 반드시 다음 형식으로 인용 비교를 적어라:
  형식: "concept='...' / ending='...' → 모순" 또는 "→ 일치"
모호한 평어("자연스럽다", "흐름이 좋다", "잘 어울린다") 금지.

[절대 반려 규칙]
- 장르 불일치 (concept 헌터물 ↔ ending 학원 로맨스 등) → 즉시 반려
- protagonist 이름 누락 → 즉시 반려
- forbidden 항목이 엔딩에 등장 → 즉시 반려
- 막 range가 [1,total]을 덮지 못함 → 즉시 반려
- 막 climax 강도가 역행(3막보다 2막이 격함) → 즉시 반려

[학습 예시 1 — 통과]
concept: {"logline":"F급 짐꾼이 시스템 버그를 발견해 S급으로 각성","genre":"헌터물","total_chapters":100,"protagonist":"강이준","keywords":["시스템물","각성물"],"forbidden":["성적 묘사"]}
ending: {"summary":"강이준이 시스템의 감독자를 처단하고 진명 시스템을 인류에 개방한다","act3_climax":"강이준이 회장을 베고 감독자 권한을 탈취","acts":[{"name":"1막","range":[1,33],"summary":"F급 짐꾼 강이준이 시스템 버그를 인지","climax":"첫 진명 발동으로 D급 던전 클리어"},{"name":"2막","range":[34,67],"summary":"길드 정치와 감독자의 추적","climax":"동료 박세린이 회장 측에 납치"},{"name":"3막","range":[68,100],"summary":"회장 처단 후 감독자 본체와 대결","climax":"강이준이 회장을 베고 감독자 권한을 탈취"}]}
판정 근거: 장르 일치(헌터물=헌터물), protagonist 강이준 등장, range [1,33]+[34,67]+[68,100]=[1,100] 완전 커버, climax 강도 1막(D급 클리어) < 2막(동료 납치) < 3막(회장 처단+권한 탈취) 정상 상승.
출력: {"판정":"통과","점수":9,"이유":"concept='헌터물·강이준·각성물' / ending='강이준이 회장 처단·감독자 권한 탈취' → 장르·주인공·키워드 모두 일치, 막 range [1,33]+[34,67]+[68,100]=완전 커버, climax 강도 정상 상승","수정가이드":""}

[학습 예시 2 — 반려 (장르 불일치 + range 결손)]
concept: {"logline":"F급 짐꾼이 시스템 버그를 발견해 S급으로 각성","genre":"헌터물","total_chapters":100,"protagonist":"강이준"}
ending: {"summary":"강이준과 박세린이 결혼해 평범한 회사원으로 살아간다","act3_climax":"두 사람의 결혼식","acts":[{"name":"1막","range":[1,30],"summary":"학원에서 만남","climax":"고백"},{"name":"2막","range":[31,60],"summary":"갈등","climax":"이별"},{"name":"3막","range":[70,100],"summary":"재회","climax":"결혼"}]}
판정 근거: 장르 헌터물 ↔ 엔딩 학원 로맨스(결혼 결말) 정반대. range도 [61,69] 누락. 1막 climax(고백)→2막 climax(이별)→3막 climax(결혼)은 강도가 아닌 감정 흐름이라 헌터물 climax 강도 기준에서 무의미.
출력: {"판정":"반려","점수":1,"이유":"concept='헌터물·시스템 버그·각성' / ending='학원 로맨스·결혼 결말' → 장르 정반대. 막 range [1,30]+[31,60]+[70,100]에서 [61,69] 결손","수정가이드":"엔딩을 헌터물 카타르시스(시스템 권한 탈취/감독자 처단 등)로 재구성하고, 막 range를 [1,33]+[34,67]+[68,100]로 100화 완전 커버"}

[학습 예시 3 — 반려 (climax 강도 역행)]
concept: {"logline":"F급 짐꾼이 각성","genre":"헌터물","total_chapters":100,"protagonist":"강이준"}
ending: {"summary":"강이준이 시스템의 비밀을 폭로한다","act3_climax":"기자회견","acts":[{"name":"1막","range":[1,33],"summary":"각성","climax":"S급 보스 솔로킬"},{"name":"2막","range":[34,67],"summary":"길드 결성","climax":"길드 회의 개최"},{"name":"3막","range":[68,100],"summary":"폭로","climax":"기자회견에서 발표"}]}
판정 근거: 1막 climax(S급 보스 솔로킬) > 3막 climax(기자회견) — 강도 역행. 헌터물 카타르시스로서 3막이 가장 약함.
출력: {"판정":"반려","점수":3,"이유":"concept='헌터물 각성' / ending climax 1막='S급 보스 솔로킬' > 3막='기자회견' → 강도 역행","수정가이드":"3막 climax를 1막보다 격하게 (예: 시스템 본체 처단 또는 신권력 구도 전복) 재설계, 1막 climax는 D급/C급 범위로 낮춤"}
"""


def build_ending_lock_prompt(concept: dict, ending: dict) -> str:
    """엔딩 생성 직후 — concept 대비 정합 검수."""
    concept_json = json.dumps(concept, ensure_ascii=False, indent=2)
    ending_json = json.dumps(ending, ensure_ascii=False, indent=2)
    return (
        "[검수자 역할]\n엔딩 잠금 검수자\n\n"
        f"{_ENDING_LOCK_INSTRUCTION}\n\n"
        f"{_KOREAN_LOC_RULE}"
        f"[concept]\n{concept_json}\n\n"
        f"[ending]\n{ending_json}\n\n"
        f"{_OUTPUT_HINT}"
    )


# ---------------------------------------------------------------------------
# 2) EndingLockReviewer.review_against_skeleton — ending ↔ 100화 끝
# ---------------------------------------------------------------------------

_ENDING_VS_SKELETON_INSTRUCTION = """[검수 대상]
엔딩(1줄 엔딩 + 3막 climax)이 100화 줄거리(plot_skeleton)의 끝과 일치하는지 본다.
중간 화의 흐름·문장력·재미는 보지 마라. 막 경계 화와 마지막 화만 본다.

[검사 항목]
1. skeleton의 마지막 화(chapter_n=total) overall이 ending["summary"] 및 ending["act3_climax"]와 일치하는가
   - 마지막 화 overall이 엔딩 사건을 직접 다루어야 함 (회수/봉합/카타르시스).
2. 막별 마지막 화(예: ch33, ch67, ch100)의 overall이 해당 막의 climax와 일치하는가
   - ending["acts"][i]["range"][1] 화의 overall ↔ ending["acts"][i]["climax"]
3. 일치하지 않으면 반려 + 수정가이드에 어느 화를 어떻게 고쳐야 하는지 명시
   - 형식: "ch{번호} overall='...' / 막{i} climax='...' → 불일치, ch{번호}을 …로 수정"

[필수 출력 규칙]
"이유"에 반드시 인용 비교를 적어라:
  형식: "ch100 overall='...' / ending summary='...' → 일치/불일치"
모호한 평어 금지.

[절대 반려 규칙]
- 마지막 화 overall이 엔딩 사건을 전혀 다루지 않음 → 즉시 반려
- 막 경계 화 overall이 해당 막 climax와 다른 사건 → 즉시 반려

[학습 예시 1 — 통과]
ending: {"summary":"강이준이 감독자를 처단하고 진명 시스템을 인류에 개방","act3_climax":"강이준이 회장을 베고 감독자 권한 탈취","acts":[{"range":[1,33],"climax":"첫 진명 발동으로 D급 던전 클리어"},{"range":[34,67],"climax":"동료 박세린이 회장 측에 납치"},{"range":[68,100],"climax":"강이준이 회장을 베고 감독자 권한 탈취"}]}
경계 화 overall:
  ch33: "강이준이 첫 진명을 발동해 D급 던전을 단독 클리어, 시스템이 이상 반응을 보인다"
  ch67: "박세린이 회장 측에 납치되고 강이준은 추적 단서를 잡는다"
  ch100: "강이준이 회장을 처단하고 감독자 권한을 탈취해 진명 시스템을 인류에 개방한다"
판정 근거: ch33↔1막 climax 일치, ch67↔2막 climax 일치, ch100↔3막 climax+엔딩 일치.
출력: {"판정":"통과","점수":9,"이유":"ch33='D급 단독 클리어, 시스템 이상 반응' / 1막 climax 일치, ch67='박세린 납치' / 2막 climax 일치, ch100='회장 처단·권한 탈취·인류 개방' / 엔딩+3막 climax 모두 일치","수정가이드":""}

[학습 예시 2 — 반려 (마지막 화 엔딩 미회수)]
ending: {"summary":"강이준이 감독자를 처단","act3_climax":"강이준이 회장을 베고 감독자 권한 탈취","acts":[{"range":[1,33],"climax":"첫 진명"},{"range":[34,67],"climax":"박세린 납치"},{"range":[68,100],"climax":"회장 처단"}]}
경계 화 overall:
  ch33: "강이준이 첫 진명을 발동"
  ch67: "박세린이 납치된다"
  ch100: "강이준이 길드 사무실에서 일상을 보내며 새로운 의뢰를 받는다"
판정 근거: ch100 overall이 엔딩(감독자 처단)과 무관한 일상 묘사. 3막 climax(회장 처단) 미회수.
출력: {"판정":"반려","점수":2,"이유":"ch100='길드 사무실 일상·새 의뢰' / ending summary='감독자 처단' → 엔딩 미회수, 3막 climax='회장 처단'도 본문에 등장 안 함","수정가이드":"ch100 overall을 '강이준이 회장을 베고 감독자 권한을 탈취해 진명 시스템을 인류에 개방하는 카타르시스'로 재작성. 일상 의뢰 묘사는 ch99 이전으로 이동"}
"""


def build_ending_vs_skeleton_prompt(ending: dict, skeleton: list[dict]) -> str:
    """100화 골격 완성 후 — 엔딩과 끝 일치 검수.

    토큰 절약을 위해 skeleton 전체를 보내지 않고 막 경계 화와 마지막 화만 추출.
    """
    ending_json = json.dumps(ending, ensure_ascii=False, indent=2)

    # 경계 화만 추출 — ending["acts"][i]["range"][1] 화 + 마지막 화
    boundary_ns: list[int] = []
    for act in ending.get("acts", []):
        rng = act.get("range") or [0, 0]
        if isinstance(rng, list) and len(rng) == 2:
            boundary_ns.append(int(rng[1]))
    if skeleton:
        last_n = max((int(c.get("chapter_n", 0)) for c in skeleton), default=0)
        if last_n and last_n not in boundary_ns:
            boundary_ns.append(last_n)
    boundary_ns = sorted(set(boundary_ns))

    by_n = {int(c.get("chapter_n", 0)): c for c in skeleton}
    boundary_lines = []
    for n in boundary_ns:
        ch = by_n.get(n)
        if ch is None:
            boundary_lines.append(f"ch{n}: (누락)")
        else:
            overall = str(ch.get("overall", "")).strip().replace("\n", " ")
            boundary_lines.append(f"ch{n}: \"{overall}\"")
    boundary_block = "\n".join(boundary_lines) if boundary_lines else "(경계 화 추출 실패)"

    return (
        "[검수자 역할]\n엔딩 ↔ 100화 끝 정합 검수자\n\n"
        f"{_ENDING_VS_SKELETON_INSTRUCTION}\n\n"
        f"{_KOREAN_LOC_RULE}"
        f"[ending]\n{ending_json}\n\n"
        f"[막 경계 화 + 마지막 화 overall]\n{boundary_block}\n\n"
        f"{_OUTPUT_HINT}"
    )


# ---------------------------------------------------------------------------
# 3) OutlineConsistencyReviewer.review_act — concept ↔ ending ↔ skeleton_act
# ---------------------------------------------------------------------------

_OUTLINE_CONSISTENCY_INSTRUCTION = """[검수 대상]
한 막에 해당하는 화들(skeleton_act)이 concept·ending["acts"][act_idx]와 모순 없는지 본다.
다른 막은 미완성일 수 있으므로 보지 마라.

[검사 항목]
1. skeleton_act 길이 일치
   - skeleton_act의 화 개수 == ending["acts"][act_idx]["range"]의 (끝-시작+1)
   - 일치하지 않으면 즉시 반려.
2. 각 화 overall이 해당 막 summary 범주 안에 있는가
   - 장르(concept["genre"]) · 톤(concept["mood"]) · 세계관(헌터물/시스템물 등) 모순 없어야 함.
   - 막 summary와 무관한 사건이 다수면 반려.
3. 화 사이 흐름이 자연스러운가
   - i화 끝과 i+1화 시작이 끊기는지 — overall 키워드 흐름 (인물·장소·진행 사건).
   - 시간/공간 점프나 인물 갑작스런 등장/소멸이 보이면 반려.
4. protagonist 등장 + forbidden 미등장
   - concept["protagonist"]가 막 전체에서 한 번도 등장하지 않으면 즉시 반려.
   - concept["forbidden"] 요소가 어느 화에든 등장하면 즉시 반려.
5. 한글화 규칙 (게임표준어 외 영문)
   - "어쌔신/탱커/Assassin/Tanker/STR/DEX/INT/HP/MP" 등이 overall에 영문으로 적혀 있으면 반려.
   - 마나/길드/던전/헌터/보스/레이드/파티는 OK.

[필수 출력 규칙]
"이유"에 반드시 인용 비교 또는 화 번호 + 인용을 적어라:
  형식: "ch{n} overall='...' / 막{i} summary='...' → 모순" 또는 "→ 일치"
모호한 평어 금지.

[절대 반려 규칙]
- skeleton_act 길이 ≠ range 길이 → 즉시 반려
- protagonist가 막 전체에 0회 등장 → 즉시 반려
- forbidden 요소 등장 → 즉시 반려
- 영문 약어/단어(어쌔신·탱커·STR 등) 등장 → 즉시 반려
- 화 사이 명백한 흐름 단절 (예: ch5에서 던전 진입 → ch6에서 사전 통보 없이 다른 도시) → 반려

[학습 예시 1 — 통과 (1막)]
concept: {"genre":"헌터물","mood":"다크코미디","protagonist":"강이준","forbidden":["성적 묘사"]}
act_idx: 0
ending["acts"][0]: {"name":"1막","range":[1,5],"summary":"F급 짐꾼 강이준이 시스템 버그를 인지","climax":"첫 진명 발동으로 D급 던전 클리어"}
skeleton_act:
  ch1: "강이준이 길드 사무실에서 D급 던전 의뢰를 받아 짐꾼으로 출발"
  ch2: "던전 진입로에서 강이준이 시스템 메시지의 미세한 어긋남을 처음 감지"
  ch3: "강이준이 보스방 직전 길드원들과 대치, 짐꾼 묘사 강조"
  ch4: "강이준이 보스방 진입, 시스템 버그를 의도적으로 자극해 첫 진명 단서를 발견"
  ch5: "강이준이 첫 진명을 발동해 D급 보스를 단독 처치, 시스템이 이상 반응"
판정 근거: 길이 5 == range(1,5) 길이 5 OK. 모든 화에 강이준 등장. 1막 summary(시스템 버그 인지)와 climax(첫 진명) 정상 도달. 흐름 단절 없음. 영문 약어 없음.
출력: {"판정":"통과","점수":9,"이유":"ch1~ch5 모두 강이준 등장, 1막 summary='시스템 버그 인지'와 일치, ch5 climax='첫 진명·D급 단독' 일치, 화 흐름 단절 없음","수정가이드":""}

[학습 예시 2 — 반려 (길이 불일치 + 영문 약어)]
concept: {"genre":"헌터물","protagonist":"강이준"}
act_idx: 0
ending["acts"][0]: {"range":[1,5],"summary":"F급 짐꾼 각성 단서","climax":"첫 진명"}
skeleton_act:
  ch1: "강이준이 어쌔신 길드원과 동행"
  ch2: "강이준의 STR 스탯이 상승"
  ch3: "강이준이 첫 진명 발동"
판정 근거: 길이 3 ≠ range 길이 5 → 즉시 반려. 추가로 ch1 '어쌔신'(영문 표기)과 ch2 'STR 스탯' 영문 약어 등장 → 한글화 규칙 위반.
출력: {"판정":"반려","점수":1,"이유":"skeleton_act 길이=3 ≠ range(1,5) 길이=5 → 길이 불일치. 추가 위반: ch1='어쌔신', ch2='STR 스탯' 영문 표기 → 한글화 규칙 위반","수정가이드":"화 2개 추가해 5화로 맞추고, '어쌔신'→'암살자', 'STR 스탯'→'근력' 한글로 교체"}

[학습 예시 3 — 반려 (protagonist 미등장 + 흐름 단절)]
concept: {"genre":"헌터물","protagonist":"강이준","forbidden":["성적 묘사"]}
act_idx: 1
ending["acts"][1]: {"range":[34,38],"summary":"길드 정치와 감독자의 추적","climax":"동료 박세린이 회장 측에 납치"}
skeleton_act:
  ch34: "박세린이 길드 회의에 참석"
  ch35: "회장이 자기 사무실에서 감독자 보고를 받음"
  ch36: "박세린이 시장에서 정보 수집"
  ch37: "회장과 감독자가 회동"
  ch38: "박세린이 회장 측에 납치된다"
판정 근거: 길이 5=5 OK. 그러나 protagonist 강이준이 1막 전체에서 0회 등장 → 즉시 반려. 추가로 ch36(시장)→ch37(회장-감독자 회동)이 인물·장소 전환 단서 없이 점프.
출력: {"판정":"반려","점수":2,"이유":"protagonist 강이준이 ch34~ch38 모두 미등장 → 막 전체 0회. 추가 ch36='박세린 시장' / ch37='회장-감독자 회동' 사이 흐름 단절","수정가이드":"각 화에 강이준 시점/등장 추가(예: ch34 강이준이 회의 밖에서 단서 추적, ch37 강이준이 박세린의 부재를 감지). ch36→ch37 전환에 강이준 추적선 비트 삽입"}
"""


def build_outline_consistency_prompt(
    concept: dict,
    ending: dict,
    skeleton_act: list[dict],
    *,
    act_idx: int,
) -> str:
    """막 단위 줄거리 정합 검수 프롬프트."""
    concept_slim = {
        "genre": concept.get("genre", ""),
        "mood": concept.get("mood", ""),
        "total_chapters": concept.get("total_chapters", 0),
        "protagonist": concept.get("protagonist", ""),
        "keywords": concept.get("keywords", []),
        "forbidden": concept.get("forbidden", []),
    }
    concept_json = json.dumps(concept_slim, ensure_ascii=False, indent=2)

    acts = ending.get("acts", [])
    act = acts[act_idx] if 0 <= act_idx < len(acts) else {}
    act_json = json.dumps(act, ensure_ascii=False, indent=2)

    # skeleton_act은 한 막의 화 리스트만. 그대로 ch{n}: "overall" 형태로 펼침.
    skeleton_lines = []
    for ch in skeleton_act:
        n = int(ch.get("chapter_n", 0))
        overall = str(ch.get("overall", "")).strip().replace("\n", " ")
        skeleton_lines.append(f"ch{n}: \"{overall}\"")
    skeleton_block = "\n".join(skeleton_lines) if skeleton_lines else "(빈 막)"

    return (
        f"[검수자 역할]\n줄거리 정합 검수자 (act_idx={act_idx} → {act_idx + 1}막)\n\n"
        f"{_OUTLINE_CONSISTENCY_INSTRUCTION}\n\n"
        f"{_KOREAN_LOC_RULE}"
        f"[concept (slim)]\n{concept_json}\n\n"
        f"[ending.acts[{act_idx}]]\n{act_json}\n\n"
        f"[skeleton_act ({len(skeleton_act)}화)]\n{skeleton_block}\n\n"
        f"{_OUTPUT_HINT}"
    )
