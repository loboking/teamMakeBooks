# M1 인터페이스 명세 (개발 임시 — M3 이후 폐기 가능)

이 문서는 M1 멀티 에이전트 병렬 개발의 **인터페이스 합의서**입니다.
세 모듈(meta_writer / meta_reviewer / meta_graph+CLI)의 함수·클래스 시그니처를 미리 못 박아 둡니다. 구현 에이전트는 이 시그니처를 정확히 따릅니다.

---

## 0. 모델·설정 — 이미 추가됨

`config.yaml` 추가 항목:
- `teams.meta_writer.{concept,ending,plot_skeleton}.model = "ollama:gemma4:e2b"`
- `teams.meta_reviewer.{ending_lock,outline_consistency}.model = "ollama:gemma4:e2b"`
- `meta_writer.{concept,ending,plot_skeleton}_{temperature,num_predict}`
- `meta_reviewer.{temperature,num_predict}`

`Settings.model_key("meta_writer", "ending")` 형태로 접근.

---

## 1. MetaState (LangGraph TypedDict)

```python
from pathlib import Path
from typing import Any, TypedDict


class MetaState(TypedDict):
    settings: Any  # Settings 인스턴스 (직렬화 불필요)

    # 사용자 입력 (raw)
    concept_input: dict   # {"logline": "...", "genre": "...", "mood": "...",
                          #  "total_chapters": 100, "protagonist": "강이준",
                          #  "keywords": [...], "forbidden": [...],
                          #  "reference_tone": "...", "work_id": None|"..."}

    # 결정된 work_id (concept 정규화 후)
    work_id: str

    # 단계별 산출물
    concept: dict | None         # 정규화된 컨셉
    ending: dict | None          # {"summary": str, "act3_climax": str,
                                 #  "acts": [{"name":"1막","range":[1,33], "summary": str, "climax": str}, ...]}
    plot_skeleton: list[dict] | None
                                 # [{"chapter_n": int, "act": int, "overall": str}, ...] 길이 = total_chapters

    # 검수
    review_history: list[dict]   # 각 스테이지의 검수 결과 누적
    retry_counts: dict[str, int] # {"ending_lock": N, "outline_consistency_act1": N, ...}

    # 진행
    current_stage: str           # "init_concept" | "ending_lock" | "plot_act1" | "plot_act2" | "plot_act3" | "ending_recheck" | "save" | "__halt__"
    success: bool
    failure_stage: str | None
    failure_reason: str | None

    # 산출 경로 (M1: novels/{work_id}/_init/*.yaml)
    init_dir: Path | None        # novels/{work_id}/_init/

    started_at: str
```

---

## 2. meta_writer — 신규 모듈

위치: `backend/app/teams/meta_writer/`

```
backend/app/teams/meta_writer/
├── __init__.py        # MetaWriterAgent re-export
├── agent.py           # MetaWriterAgent 클래스
└── prompts.py         # build_*_prompt 함수들
```

### 2.1 `MetaWriterAgent` (단일 클래스, 역할별 메서드)

```python
class MetaWriterAgent:
    def __init__(
        self,
        provider: LLMProvider,
        *,
        temperature: float = 0.5,
        num_predict: int = 2000,
        logs_dir: Path | None = None,
    ): ...

    # 단계 1: 사용자 입력을 정규화 + work_id 생성 + 누락 옵션 보충
    def normalize_concept(self, concept_input: dict, work_id: str) -> dict: ...
    # 반환: {
    #   "logline": str, "genre": str, "mood": str, "total_chapters": int,
    #   "protagonist": str, "keywords": [str], "forbidden": [str],
    #   "reference_tone": str, "work_id": str,
    #   "summary": str  (LLM이 정리한 컨셉 요약 3~5줄)
    # }

    # 단계 2: 엔딩 + 3막 골격
    def generate_ending(self, concept: dict, work_id: str) -> dict: ...
    # 반환: {
    #   "summary": str (엔딩 1줄),
    #   "act3_climax": str (3막 클라이맥스 1~2줄),
    #   "acts": [
    #     {"name":"1막","range":[1,33], "summary": str, "climax": str},
    #     {"name":"2막","range":[34,67], "summary": str, "climax": str},
    #     {"name":"3막","range":[68,100], "summary": str, "climax": str},
    #   ]
    # }

    # 단계 3: 막 단위 100화 줄거리 — 각 화별 overall 200~300자
    def generate_plot_skeleton(
        self, concept: dict, ending: dict,
        *, act_idx: int, work_id: str,
    ) -> list[dict]: ...
    # act_idx: 0|1|2  → ending["acts"][act_idx]의 range를 그대로 사용
    # 반환: [{"chapter_n": int, "act": int, "overall": str}, ...] 길이 = range(끝-시작+1)

    # revise — 피드백을 받아 재생성
    def revise_concept(self, concept: dict, feedback: str, work_id: str) -> dict: ...
    def revise_ending(self, ending: dict, feedback: str, concept: dict, work_id: str) -> dict: ...
    def revise_plot_act(
        self, skeleton_act: list[dict], feedback: str,
        concept: dict, ending: dict, *, act_idx: int, work_id: str,
    ) -> list[dict]: ...
```

### 2.2 출력 JSON 스키마 (gemma4 format_schema 사용)

LLM 호출 시 `format_schema=`로 강제. 각 메서드별 스키마는 prompts.py에 정의:
- `CONCEPT_SCHEMA`
- `ENDING_SCHEMA`
- `PLOT_ACT_SCHEMA` (한 막 내 화 리스트)

### 2.3 프롬프트

`prompts.py`에 `build_concept_prompt`, `build_ending_prompt`, `build_plot_act_prompt`, 각각의 `build_*_revise_prompt`. 톤·금지 규칙(메모리: "게임표준어 마나/길드/던전/헌터 유지, 어쌔신/탱커/스탯약어는 한글로", "100화 종결")을 시스템 지침에 포함.

### 2.4 로깅

기존 `log_call(team="meta_writer", role="<concept|ending|plot_act{N}|revise_*>", work_id=..., chapter_n=0, ...)` 사용.

---

## 3. meta_reviewer — 신규 모듈

위치: `backend/app/teams/reviewer/meta_reviewers.py`
프롬프트: `backend/app/teams/reviewer/meta_prompts.py`

기존 `ReviewResult` 데이터클래스 그대로 재사용.

```python
from .agent import ReviewResult
# ReviewResult(role, attempt, passed, score, reason, feedback, raw, parse_error)


class EndingLockReviewer:
    """엔딩과 컨셉/3막 골격이 일관된지, 그리고 100화 끝이 엔딩과 일치하는지 검수."""

    def __init__(
        self,
        provider: LLMProvider,
        *,
        temperature: float = 0.2,
        num_predict: int = 800,
        logs_dir: Path | None = None,
    ): ...

    # 사용 시점 1: ending 생성 직후 — concept 대비
    def review_ending(self, concept: dict, ending: dict, *, attempt: int, work_id: str) -> ReviewResult: ...

    # 사용 시점 2: plot_skeleton 100화 모두 완성 후 — 끝(마지막 화) ↔ 엔딩 일치
    def review_against_skeleton(
        self, ending: dict, skeleton: list[dict],
        *, attempt: int, work_id: str,
    ) -> ReviewResult: ...


class OutlineConsistencyReviewer:
    """concept ↔ ending ↔ plot_skeleton(해당 막) 모순 검수."""

    def __init__(
        self,
        provider: LLMProvider,
        *,
        temperature: float = 0.2,
        num_predict: int = 800,
        logs_dir: Path | None = None,
    ): ...

    # act_idx 막에 대해서만 검수 (다른 막은 미완성일 수 있음)
    def review_act(
        self,
        concept: dict, ending: dict, skeleton_act: list[dict],
        *, act_idx: int, attempt: int, work_id: str,
    ) -> ReviewResult: ...
```

검수 출력 JSON 스키마는 기존 `REVIEW_SCHEMA` 그대로 (`{"판정","점수","이유","수정가이드"}`).

---

## 4. meta_graph + CLI

### 4.1 그래프 위치

`backend/app/orchestrator/meta_graph.py` (graph.py와 별도 모듈, 동일 디렉토리).

### 4.2 노드 흐름 (M1 범위)

```
init_concept              ← MetaWriterAgent.normalize_concept
   ↓
ending_lock               ← MetaWriterAgent.generate_ending
   ↓
ending_lock_review        ← EndingLockReviewer.review_ending  (revise loop, max_retries)
   ↓
plot_act1                 ← MetaWriterAgent.generate_plot_skeleton(act_idx=0)
   ↓
outline_consistency_act1  ← OutlineConsistencyReviewer.review_act(act_idx=0)  (revise loop)
   ↓
plot_act2                 ← act_idx=1
   ↓
outline_consistency_act2
   ↓
plot_act3                 ← act_idx=2
   ↓
outline_consistency_act3
   ↓
ending_recheck            ← EndingLockReviewer.review_against_skeleton  (revise → revise_plot_act 3막)
   ↓
save_intermediate         ← novels/{work_id}/_init/{concept,ending,plot_skeleton}.yaml
   ↓
END
```

실패 시 `meta_alert_and_halt` → `logs/failures/meta_{work_id}_{stage}.json` + 텔레그램.

### 4.3 진입 함수

```python
def invoke_meta_pipeline(
    concept_input: dict,
    *,
    settings: Settings,
    work_id: str | None = None,  # None이면 logline에서 자동 슬러그
) -> MetaState: ...
```

### 4.4 CLI: `scripts/init_work.py`

```bash
# 단계 검토 모드 (기본)
.venv/bin/python scripts/init_work.py --logline "F급 짐꾼이 시스템 버그를 발견해 S급으로 각성" \
    --genre 헌터물 --total 100 --protagonist 강이준

# 자동 모드
.venv/bin/python scripts/init_work.py --logline "..." --auto

# yaml 입력
.venv/bin/python scripts/init_work.py --input concept.yaml [--auto]

# dry-run (LLM 호출 없음, 디렉토리·스키마만 검증)
.venv/bin/python scripts/init_work.py --logline "..." --dry-run
```

산출:
- 진행 단계마다 stdout 진행 출력
- 단계 검토 모드: 결과 미리보기 + `[Enter] 다음 / [r] 재생성 / [e] 직접 편집 / [q] 중단`
- 완료 시 `novels/{work_id}/_init/concept.yaml`, `ending.yaml`, `plot_skeleton.yaml` 저장
- 실패 시 `logs/failures/meta_*.json` + 종료 코드 1

### 4.5 출력 파일 스키마 (M1)

```yaml
# novels/{work_id}/_init/concept.yaml
work_id: modern_fantasy_xxx
logline: "..."
genre: 헌터물
mood: 다크코미디
total_chapters: 100
protagonist: 강이준
keywords: [시스템물, 각성물]
forbidden: [성적 묘사]
reference_tone: ""
summary: "...(3~5줄)..."
```

```yaml
# novels/{work_id}/_init/ending.yaml
summary: "엔딩 1줄"
act3_climax: "3막 클라이맥스 1~2줄"
acts:
  - name: 1막
    range: [1, 33]
    summary: "..."
    climax: "..."
  - name: 2막
    range: [34, 67]
    summary: "..."
    climax: "..."
  - name: 3막
    range: [68, 100]
    summary: "..."
    climax: "..."
```

```yaml
# novels/{work_id}/_init/plot_skeleton.yaml
total: 100
chapters:
  - chapter_n: 1
    act: 1
    overall: "...(200~300자)..."
  - chapter_n: 2
    act: 1
    overall: "..."
  ...
  - chapter_n: 100
    act: 3
    overall: "..."
```

---

## 5. 코드 컨벤션 (모든 에이전트 공통)

- `from __future__ import annotations` 첫 줄
- 한국어 주석/독스트링 (기존 코드 톤)
- 타입 힌트 필수 (3.11+ 문법 OK)
- `LLMProvider.complete()`만 사용. ollama 직접 호출 금지.
- 로깅은 반드시 `log_call(...)` 사용. logs_dir 주어진 경우만.
- 모델 키는 `settings.model_key("meta_writer", "ending")` 식
- 실패 시 `LLMProviderError` 그대로 전파. 메타 그래프에서 잡아 `__halt__` 처리.
- 토큰 절약: 프롬프트는 컨텍스트 짧게 유지. 100화 plot은 막 단위 분할.
- 메모리 규칙 반영:
  - 게임표준어 유지: 마나/길드/던전/헌터
  - 한글로: 어쌔신/탱커/스탯약어
  - 100화 종결 가정
