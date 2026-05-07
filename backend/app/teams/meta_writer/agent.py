"""메타 작가 에이전트 — 컨셉 정규화 + 엔딩+3막 + 막 단위 100화 줄거리 생성.

회차 파이프라인이 빈 템플릿에서 출발하지 않도록, logline 1줄에서
회차 outlines까지 자동으로 채우는 메타 파이프라인의 핵심 모듈.

- 모든 LLM 호출은 ollama format_schema로 JSON을 강제.
- 막 단위 분할 생성으로 gemma4:e2b 짧은 컨텍스트 한계 회피.
- WriterAgent와 동일한 패턴 (revise는 기존 결과 + 피드백 동시 입력).
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from ...providers import LLMProvider, LLMProviderError
from ...utils.logger import log_call
from .prompts import (
    BEAT_EXPAND_SCHEMA,
    CHARACTERS_SCHEMA,
    CONCEPT_SCHEMA,
    ENDING_SCHEMA,
    NAMING_TABLE_SCHEMA,
    PERSONA_SCHEMA,
    PLOT_ACT_SCHEMA,
    PLOT_CHAPTER_SCHEMA,
    WORLD_BIBLE_SCHEMA,
    build_beat_expand_prompt,
    build_characters_prompt,
    build_concept_prompt,
    build_concept_revise_prompt,
    build_ending_prompt,
    build_ending_revise_prompt,
    build_naming_table_prompt,
    build_persona_prompt,
    build_plot_act_prompt,
    build_plot_act_revise_prompt,
    build_plot_chapter_prompt,
    build_plot_chapter_revise_prompt,
    build_world_bible_prompt,
)


# ---------------------------------------------------------------------------
# work_id 자동 생성 — logline에서 키워드 + 장르 prefix + 6자리 해시
# ---------------------------------------------------------------------------

# 장르 → work_id prefix (영문 소문자/언더스코어)
_GENRE_PREFIX_MAP = {
    "헌터물": "hunter",
    "헌터": "hunter",
    "판타지": "fantasy",
    "현대판타지": "modern_fantasy",
    "modern_fantasy": "modern_fantasy",
    "무협": "wuxia",
    "회귀": "regression",
    "로맨스": "romance",
    "정통무협": "wuxia",
    "스포츠": "sports",
    "전쟁": "war",
}

# logline에서 의미 키워드 추출 시 무시할 한국어 불용어
_STOPWORDS = {
    "있다", "없다", "되다", "하다", "이다", "그", "그녀", "주인공",
    "이야기", "스토리", "소설", "작품", "을", "를", "이", "가",
    "는", "은", "의", "에", "에서", "으로", "로", "와", "과",
    "도", "만", "또", "그리고", "그러나", "다시", "그", "이",
}


def _slug_from_text(text: str) -> list[str]:
    """텍스트에서 의미 단어 추출 — 한글/영문 단어 단위, 불용어/조사 제거."""
    # 한글 단어, 영문 단어 분리
    tokens = re.findall(r"[가-힣]{2,}|[A-Za-z][A-Za-z0-9]+", text)
    out: list[str] = []
    for t in tokens:
        if t in _STOPWORDS:
            continue
        if len(t) < 2:
            continue
        out.append(t)
    return out


def _ascii_keyword(token: str) -> str:
    """한글 토큰을 ASCII로 환산 — 매핑 없으면 hash 6자."""
    # 자주 등장하는 한국 헌터물 단어만 직접 매핑 (가독성 ↑)
    direct = {
        "짐꾼": "porter",
        "헌터": "hunter",
        "각성": "awaken",
        "시스템": "system",
        "버그": "bug",
        "복수": "revenge",
        "회귀": "regression",
        "던전": "dungeon",
        "길드": "guild",
        "마나": "mana",
        "정점": "apex",
        "관리자": "admin",
        "감독자": "overseer",
        "무등급": "rankless",
        "회장": "chairman",
    }
    if token in direct:
        return direct[token]
    # 영문은 그대로 소문자
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9]+", token):
        return token.lower()
    return ""


def _auto_work_id(concept_input: dict) -> str:
    """logline에서 키워드 2~3개 + 장르 prefix + 6자리 해시.

    예: 'F급 짐꾼이 시스템 버그를 발견해 S급으로 각성', genre='헌터물'
        → 'hunter_porter_system_a3f2b1'
    """
    logline = str(concept_input.get("logline", "")).strip()
    genre = str(concept_input.get("genre", "")).strip()

    prefix = _GENRE_PREFIX_MAP.get(genre, "")
    if not prefix:
        # 장르 매핑 실패 시 'work'로 폴백
        prefix = "work" if not genre else re.sub(r"[^a-z0-9]+", "", genre.lower()) or "work"

    keywords: list[str] = []
    for tok in _slug_from_text(logline):
        ascii_kw = _ascii_keyword(tok)
        if ascii_kw and ascii_kw not in keywords and ascii_kw != prefix:
            keywords.append(ascii_kw)
        if len(keywords) >= 3:
            break

    # 안정적 6자리 해시 (logline + protagonist 기반)
    seed = f"{logline}|{concept_input.get('protagonist', '')}|{genre}"
    h = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:6]

    parts = [prefix] + keywords + [h]
    work_id = "_".join(p for p in parts if p)
    # 안전: 영문 소문자/숫자/언더스코어만
    work_id = re.sub(r"[^a-z0-9_]+", "", work_id)
    return work_id or f"work_{h}"


# ---------------------------------------------------------------------------
# JSON 파싱 헬퍼 — gemma4가 가끔 앞뒤에 텍스트를 흘려도 살려낸다
# ---------------------------------------------------------------------------

def _parse_json_object(text: str) -> dict:
    """LLM 응답에서 JSON object를 살려낸다. 파싱 실패 시 LLMProviderError.

    gemma4가 출력 중간에 멈추는 경우(닫는 `}` 없음)도 정규식 폴백으로
    핵심 필드(overall/content/summary)를 추출해 부분 dict 반환.
    """
    s = text.strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    # 첫 '{' ~ 마지막 '}' 슬라이스 시도
    start = s.find("{")
    end = s.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(s[start : end + 1])
        except json.JSONDecodeError:
            pass

    # 폴백: 잘린 JSON에서 핵심 string 필드 정규식 추출
    fallback: dict = {}
    for key in ("overall", "content", "summary", "name", "instruction"):
        m = re.search(rf'"{key}"\s*:\s*"((?:[^"\\]|\\.)*)', s)
        if m:
            try:
                # 따옴표 안 내용 — JSON escape 풀기 (\\n 등)
                fallback[key] = json.loads(f'"{m.group(1)}"')
            except json.JSONDecodeError:
                fallback[key] = m.group(1)
    # chapter_n / act 같은 정수 필드
    for key in ("chapter_n", "act"):
        m = re.search(rf'"{key}"\s*:\s*(\d+)', s)
        if m:
            fallback[key] = int(m.group(1))
    if fallback:
        return fallback

    raise LLMProviderError(f"메타 작가 JSON 파싱 실패 — 정규식 폴백 실패. 원문 앞부분: {s[:200]}")


# ---------------------------------------------------------------------------
# 메인 에이전트
# ---------------------------------------------------------------------------

class MetaWriterAgent:
    """단일 클래스에 단계별 메서드. WriterAgent와 동일한 패턴."""

    def __init__(
        self,
        provider: LLMProvider,
        *,
        temperature: float = 0.5,
        num_predict: int = 2000,
        logs_dir: Path | None = None,
    ):
        self.provider = provider
        self.temperature = temperature
        self.num_predict = num_predict
        self.logs_dir = logs_dir

    # ------------------------------------------------------------------
    # 1단계: 컨셉 정규화
    # ------------------------------------------------------------------
    def normalize_concept(self, concept_input: dict, work_id: str) -> dict:
        """사용자 입력 + work_id → 정규화된 컨셉 dict.

        work_id가 빈 문자열/None이면 logline에서 자동 슬러그.
        사용자가 명시한 work_id는 그대로 유지.
        """
        # work_id 결정
        explicit = (work_id or "").strip() or (concept_input.get("work_id") or "").strip()
        wid = explicit or _auto_work_id(concept_input)

        prompt = build_concept_prompt(concept_input, wid)
        resp = self.provider.complete(
            prompt,
            max_tokens=self.num_predict,
            temperature=self.temperature,
            format_schema=CONCEPT_SCHEMA,
        )
        if self.logs_dir:
            log_call(
                team="meta_writer",
                role="concept",
                work_id=wid,
                chapter_n=0,
                prompt=prompt,
                response=resp,
                logs_dir=self.logs_dir,
            )

        data = _parse_json_object(resp.text)
        # 누락/타입 보정 — 후속 노드가 안전하게 쓸 수 있도록
        # total_chapters는 사용자 입력값을 강제 우선 (LLM 환각으로 100화로 덮어쓰는 사고 방지)
        user_total = int(concept_input.get("total_chapters") or 0) or None
        llm_total = int(data.get("total_chapters") or 0) or None
        final_total = user_total or llm_total or 100
        return {
            "logline": str(data.get("logline", concept_input.get("logline", ""))),
            "genre": str(data.get("genre", concept_input.get("genre", ""))),
            "mood": str(data.get("mood", concept_input.get("mood", ""))),
            "total_chapters": final_total,
            "protagonist": str(data.get("protagonist", concept_input.get("protagonist", ""))),
            "keywords": list(data.get("keywords", concept_input.get("keywords", []) or [])),
            "forbidden": list(data.get("forbidden", concept_input.get("forbidden", []) or [])),
            "reference_tone": str(data.get("reference_tone", concept_input.get("reference_tone", "") or "")),
            "summary": str(data.get("summary", "")),
            "work_id": wid,
        }

    def revise_concept(self, concept: dict, feedback: str, work_id: str) -> dict:
        """컨셉 카드 재생성 (피드백 반영)."""
        prompt = build_concept_revise_prompt(concept, feedback, work_id)
        resp = self.provider.complete(
            prompt,
            max_tokens=self.num_predict,
            temperature=self.temperature,
            format_schema=CONCEPT_SCHEMA,
        )
        if self.logs_dir:
            log_call(
                team="meta_writer",
                role="revise_concept",
                work_id=work_id,
                chapter_n=0,
                prompt=prompt,
                response=resp,
                logs_dir=self.logs_dir,
            )
        data = _parse_json_object(resp.text)
        # total_chapters는 기존 concept 값 유지 (revise는 컨셉 자체 길이를 바꾸지 않음)
        prev_total = int(concept.get("total_chapters") or 0) or None
        llm_total = int(data.get("total_chapters") or 0) or None
        final_total = prev_total or llm_total or 100
        return {
            "logline": str(data.get("logline", concept.get("logline", ""))),
            "genre": str(data.get("genre", concept.get("genre", ""))),
            "mood": str(data.get("mood", concept.get("mood", ""))),
            "total_chapters": final_total,
            "protagonist": str(data.get("protagonist", concept.get("protagonist", ""))),
            "keywords": list(data.get("keywords", concept.get("keywords", []) or [])),
            "forbidden": list(data.get("forbidden", concept.get("forbidden", []) or [])),
            "reference_tone": str(data.get("reference_tone", concept.get("reference_tone", "") or "")),
            "summary": str(data.get("summary", concept.get("summary", ""))),
            "work_id": work_id,
        }

    # ------------------------------------------------------------------
    # 2단계: 엔딩 + 3막 골격
    # ------------------------------------------------------------------
    def generate_ending(self, concept: dict, work_id: str) -> dict:
        """엔딩 1줄 + 3막 골격(33/34/33)."""
        prompt = build_ending_prompt(concept, work_id)
        resp = self.provider.complete(
            prompt,
            max_tokens=self.num_predict,
            temperature=self.temperature,
            format_schema=ENDING_SCHEMA,
        )
        if self.logs_dir:
            log_call(
                team="meta_writer",
                role="ending",
                work_id=work_id,
                chapter_n=0,
                prompt=prompt,
                response=resp,
                logs_dir=self.logs_dir,
            )
        data = _parse_json_object(resp.text)
        return self._normalize_ending(data, concept)

    def revise_ending(self, ending: dict, feedback: str, concept: dict, work_id: str) -> dict:
        prompt = build_ending_revise_prompt(ending, feedback, concept, work_id)
        resp = self.provider.complete(
            prompt,
            max_tokens=self.num_predict,
            temperature=self.temperature,
            format_schema=ENDING_SCHEMA,
        )
        if self.logs_dir:
            log_call(
                team="meta_writer",
                role="revise_ending",
                work_id=work_id,
                chapter_n=0,
                prompt=prompt,
                response=resp,
                logs_dir=self.logs_dir,
            )
        data = _parse_json_object(resp.text)
        return self._normalize_ending(data, concept)

    @staticmethod
    def _normalize_ending(data: dict, concept: dict) -> dict:
        """엔딩 dict 보정 — acts 길이 3 강제, range 정수쌍 강제."""
        total = int(concept.get("total_chapters", 100) or 100)
        # range 기본값 (균등 분할 — 100화 기준 1~33 / 34~67 / 68~100)
        a1_end = round(total / 3)
        a2_end = round(total * 2 / 3)
        defaults = [
            {"name": "1막", "range": [1, a1_end]},
            {"name": "2막", "range": [a1_end + 1, a2_end]},
            {"name": "3막", "range": [a2_end + 1, total]},
        ]

        raw_acts = data.get("acts") or []
        acts: list[dict] = []
        for i, default in enumerate(defaults):
            src = raw_acts[i] if i < len(raw_acts) and isinstance(raw_acts[i], dict) else {}
            rng = src.get("range") or default["range"]
            try:
                rng = [int(rng[0]), int(rng[1])]
            except Exception:
                rng = default["range"]
            acts.append({
                "name": str(src.get("name") or default["name"]),
                "range": rng,
                "summary": str(src.get("summary", "")),
                "climax": str(src.get("climax", "")),
            })

        return {
            "summary": str(data.get("summary", "")),
            "act3_climax": str(data.get("act3_climax", "")),
            "acts": acts,
        }

    # ------------------------------------------------------------------
    # 3단계: 막 단위 100화 줄거리
    # ------------------------------------------------------------------
    def generate_plot_skeleton(
        self, concept: dict, ending: dict,
        *, act_idx: int, work_id: str,
    ) -> list[dict]:
        """한 막의 회차별 overall 리스트. 길이 = end - start + 1.

        화별 1회 호출 패턴 — gemma4:e2b가 긴 JSON 배열 출력에 약하므로
        회차 작가의 비트 단위 호출처럼 작은 호출 N번으로 분할.
        직전 1~2화 overall을 컨텍스트로 주입해 흐름 연속성 유지.
        """
        acts = ending.get("acts", [])
        if not (0 <= act_idx < len(acts)):
            raise LLMProviderError(f"act_idx 범위 초과: {act_idx}")
        rng = acts[act_idx].get("range", [1, 1])
        start, end = int(rng[0]), int(rng[1])
        n_chapters = end - start + 1
        act_no = act_idx + 1

        chapters: list[dict] = []
        for i, chapter_n in enumerate(range(start, end + 1)):
            prev = chapters[-2:] if chapters else None
            prompt = build_plot_chapter_prompt(
                concept, ending,
                act_idx=act_idx, chapter_n=chapter_n,
                prev_chapters=prev, work_id=work_id,
            )
            # gemma4가 가끔 빈 JSON 또는 깨진 출력을 흘림 — 1회 재시도
            overall = ""
            last_err: Exception | None = None
            for retry in range(2):
                try:
                    resp = self.provider.complete(
                        prompt,
                        max_tokens=max(self.num_predict, 800),
                        temperature=self.temperature,
                        format_schema=PLOT_CHAPTER_SCHEMA,
                    )
                    if self.logs_dir:
                        log_call(
                            team="meta_writer",
                            role=f"plot_act{act_no}_ch{chapter_n:03d}_try{retry+1}",
                            work_id=work_id,
                            chapter_n=chapter_n,
                            prompt=prompt,
                            response=resp,
                            logs_dir=self.logs_dir,
                        )
                    data = _parse_json_object(resp.text)
                    overall = str(data.get("overall", "")).strip()
                    if len(overall) >= 50:
                        break
                except LLMProviderError as e:
                    last_err = e
                    print(f"  [meta_writer] ch{chapter_n:03d} 재시도 {retry+1}/2: {e}", flush=True)
            else:
                if last_err and not overall:
                    # 2회 모두 실패 — 빈 상태로 두고 _normalize 임계 검사에 맡김
                    print(f"  [meta_writer] ch{chapter_n:03d} 빈 overall로 진행 (사후 보강 필요)", flush=True)

            chapters.append({
                "chapter_n": chapter_n,
                "act": act_no,
                "overall": overall,
            })
            if (i + 1) % 10 == 0 or i + 1 == n_chapters:
                print(f"  [meta_writer] plot_act{act_no} 진행: {i+1}/{n_chapters}화", flush=True)

        # 빈 overall 비율 검사 — 50% 초과 시 실패
        empty_n = sum(1 for c in chapters if len(c["overall"]) < 50)
        empty_ratio = empty_n / max(n_chapters, 1)
        if empty_ratio > 0.5:
            raise LLMProviderError(
                f"plot_act{act_no}: 빈/짧은 overall {empty_n}/{n_chapters}화 ({empty_ratio:.0%})."
            )
        return chapters

    def revise_plot_act(
        self, skeleton_act: list[dict], feedback: str,
        concept: dict, ending: dict,
        *, act_idx: int, work_id: str,
    ) -> list[dict]:
        prompt = build_plot_act_revise_prompt(
            skeleton_act, feedback, concept, ending,
            act_idx=act_idx, work_id=work_id,
        )
        resp = self.provider.complete(
            prompt,
            max_tokens=self.num_predict,
            temperature=self.temperature,
            format_schema=PLOT_ACT_SCHEMA,
        )
        if self.logs_dir:
            log_call(
                team="meta_writer",
                role=f"revise_plot_act{act_idx + 1}",
                work_id=work_id,
                chapter_n=0,
                prompt=prompt,
                response=resp,
                logs_dir=self.logs_dir,
            )
        data = _parse_json_object(resp.text)
        return self._normalize_plot_act(data, ending, act_idx)

    @staticmethod
    def _normalize_plot_act(data: dict, ending: dict, act_idx: int) -> list[dict]:
        """막 줄거리 보정 — chapter_n·act 강제, 길이 맞추기, overall 트리밍."""
        acts = ending.get("acts", [])
        if not (0 <= act_idx < len(acts)):
            raise LLMProviderError(f"act_idx 범위 초과: {act_idx}")
        rng = acts[act_idx].get("range", [1, 1])
        start, end = int(rng[0]), int(rng[1])
        act_no = act_idx + 1
        expected_n = end - start + 1

        chapters_raw = data.get("chapters") or []
        chapters: list[dict] = []
        for i in range(expected_n):
            chapter_n = start + i
            src = chapters_raw[i] if i < len(chapters_raw) and isinstance(chapters_raw[i], dict) else {}
            overall = str(src.get("overall", "")).strip()
            chapters.append({
                "chapter_n": chapter_n,  # 반드시 순서대로 강제
                "act": act_no,           # 반드시 막 번호 강제
                "overall": overall,
            })

        # 출력 잘림 검출 — 빈 overall 비율 30% 초과 시 즉시 실패
        empty_n = sum(1 for c in chapters if len(c["overall"]) < 50)
        empty_ratio = empty_n / max(expected_n, 1)
        if empty_ratio > 0.3:
            raise LLMProviderError(
                f"plot_act{act_no}: 빈/짧은 overall {empty_n}/{expected_n}화 ({empty_ratio:.0%}). "
                f"출력 잘림 — 청크 크기를 줄이거나 num_predict를 늘려야 함."
            )
        return chapters

    # ------------------------------------------------------------------
    # 4단계: 비트 확장 (overall → beats[3])
    # ------------------------------------------------------------------
    def expand_chapter_to_beats(
        self, concept: dict, ending: dict, chapter: dict, *, work_id: str,
    ) -> dict:
        """단일 회차 overall → overall + beats[3]. chapter_outlines/ch_n.yaml 포맷."""
        prompt = build_beat_expand_prompt(concept, ending, chapter, work_id=work_id)
        resp = self.provider.complete(
            prompt,
            max_tokens=max(self.num_predict, 4000),
            temperature=self.temperature,
            format_schema=BEAT_EXPAND_SCHEMA,
        )
        if self.logs_dir:
            log_call(
                team="meta_writer",
                role=f"beat_expand_ch{int(chapter.get('chapter_n', 0)):03d}",
                work_id=work_id,
                chapter_n=int(chapter.get("chapter_n", 0)),
                prompt=prompt,
                response=resp,
                logs_dir=self.logs_dir,
            )
        data = _parse_json_object(resp.text)
        beats_raw = data.get("beats") or []

        # 보정: 정확히 3개 강제, name 정규화
        defaults = ["intro", "development", "climax"]
        beats: list[dict] = []
        for i in range(3):
            src = beats_raw[i] if i < len(beats_raw) and isinstance(beats_raw[i], dict) else {}
            name = str(src.get("name", "")).strip() or defaults[i]
            instruction = str(src.get("instruction", "")).strip()
            beats.append({"name": name, "instruction": instruction})

        # 빈/짧은 instruction 검출 — gemma4가 짧게 줄 수 있어 200자 임계.
        # (modern_fantasy_game_01의 ch001.yaml instruction도 약 250~400자 분포)
        if any(len(b["instruction"]) < 200 for b in beats):
            raise LLMProviderError(
                f"ch{int(chapter.get('chapter_n', 0)):03d} 비트 instruction 길이 부족 "
                f"(min={min(len(b['instruction']) for b in beats)}자). 200자 미만."
            )

        return {
            "chapter_n": int(chapter.get("chapter_n", 0)),
            "overall": str(chapter.get("overall", "")),
            "beats": beats,
        }

    # ------------------------------------------------------------------
    # 5단계: 사전 자산 생성
    # ------------------------------------------------------------------
    def generate_world_bible(
        self, concept: dict, ending: dict, skeleton: list[dict], *, work_id: str,
    ) -> str:
        """world_bible.md markdown 본문 반환."""
        prompt = build_world_bible_prompt(concept, ending, skeleton, work_id=work_id)
        resp = self.provider.complete(
            prompt,
            max_tokens=max(self.num_predict, 3000),
            temperature=self.temperature,
            format_schema=WORLD_BIBLE_SCHEMA,
        )
        if self.logs_dir:
            log_call(
                team="meta_writer", role="world_bible",
                work_id=work_id, chapter_n=0,
                prompt=prompt, response=resp, logs_dir=self.logs_dir,
            )
        data = _parse_json_object(resp.text)
        content = str(data.get("content", "")).strip()
        if len(content) < 300:
            raise LLMProviderError(f"world_bible 본문 길이 부족: {len(content)}자")
        return content

    def generate_characters(
        self, concept: dict, ending: dict, skeleton: list[dict], *, work_id: str,
    ) -> list[dict]:
        """등장인물 정의 리스트."""
        prompt = build_characters_prompt(concept, ending, skeleton, work_id=work_id)
        resp = self.provider.complete(
            prompt,
            max_tokens=max(self.num_predict, 3000),
            temperature=self.temperature,
            format_schema=CHARACTERS_SCHEMA,
        )
        if self.logs_dir:
            log_call(
                team="meta_writer", role="characters",
                work_id=work_id, chapter_n=0,
                prompt=prompt, response=resp, logs_dir=self.logs_dir,
            )
        data = _parse_json_object(resp.text)
        chars = data.get("characters") or []
        if len(chars) < 3:
            raise LLMProviderError(f"등장인물 {len(chars)}명 — 최소 3명 필요")
        # 정규화
        return [
            {
                "name": str(c.get("name", "")).strip(),
                "role": str(c.get("role", "")).strip(),
                "rank": str(c.get("rank", "")).strip(),
                "job": str(c.get("job", "")).strip(),
                "personality": str(c.get("personality", "")).strip(),
                "appearance": str(c.get("appearance", "")).strip(),
                "background": str(c.get("background", "")).strip(),
                "arc": str(c.get("arc", "")).strip(),
            }
            for c in chars if c.get("name")
        ]

    def generate_naming_table(
        self, characters: list[dict], *, work_id: str,
    ) -> list[dict]:
        """호칭 쌍 리스트."""
        prompt = build_naming_table_prompt(characters, work_id=work_id)
        resp = self.provider.complete(
            prompt,
            max_tokens=max(self.num_predict, 2000),
            temperature=self.temperature,
            format_schema=NAMING_TABLE_SCHEMA,
        )
        if self.logs_dir:
            log_call(
                team="meta_writer", role="naming_table",
                work_id=work_id, chapter_n=0,
                prompt=prompt, response=resp, logs_dir=self.logs_dir,
            )
        data = _parse_json_object(resp.text)
        pairs = data.get("pairs") or []
        return [
            {
                "speaker": str(p.get("speaker", "")).strip(),
                "listener": str(p.get("listener", "")).strip(),
                "address": str(p.get("address", "")).strip(),
                "context": str(p.get("context", "")).strip(),
            }
            for p in pairs if p.get("speaker") and p.get("listener") and p.get("address")
        ]

    def generate_persona(
        self, concept: dict, *, work_id: str, author_id: str,
    ) -> dict:
        """authors/{author_id}.yaml 내용 (id/name/genre/style/tone/favorite_tropes/avoid)."""
        prompt = build_persona_prompt(concept, work_id=work_id, author_id=author_id)
        resp = self.provider.complete(
            prompt,
            max_tokens=max(self.num_predict, 1200),
            temperature=self.temperature,
            format_schema=PERSONA_SCHEMA,
        )
        if self.logs_dir:
            log_call(
                team="meta_writer", role="persona",
                work_id=work_id, chapter_n=0,
                prompt=prompt, response=resp, logs_dir=self.logs_dir,
            )
        data = _parse_json_object(resp.text)
        return {
            "id": author_id,
            "name": str(data.get("name", f"AI 작가 {author_id}")).strip(),
            "genre": str(data.get("genre", concept.get("genre", "novel"))).strip(),
            "style": str(data.get("style", "3인칭 관찰자 시점, 짧은 문장, 빠른 호흡")).strip(),
            "tone": str(data.get("tone", "한국 웹소설 톤, 시니컬·건조·타격감")).strip(),
            "favorite_tropes": list(data.get("favorite_tropes") or []),
            "avoid": list(data.get("avoid") or []) or list(concept.get("forbidden") or []),
            "sample_passages": [],
        }
