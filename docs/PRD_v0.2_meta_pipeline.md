# teamMakeBooks PRD v0.2 — 메타 파이프라인 (신규 작품 생성)

> **상태**: 1차 초안 — 2026-05-07
> **작성자**: loboking
> **목표**: 컨셉 한 줄에서 출발해 회차 파이프라인 진입 직전(작품 사전 자산 + 100화 아웃라인)까지 완전 자동화
> **모델**: gemma4:e2b (PoC 기조 유지, 단계별 분리로 짧은 컨텍스트 한계 회피)

---

## 1. 배경 — 왜 만드나

회차 파이프라인(`graph.py`)은 이미 검증됨:
`load_context → writer_draft → naming_check → reviewer×4 → polish → publisher → summary`.
검수자 4종(`direction / character / quality / repetition`)은 gemma4 짧은 컨텍스트에 맞춰 프롬프트·임계값까지 튜닝되어 있다.

그런데 회차 파이프라인의 **입력**(`chapter_outlines/ch_n.yaml`, `world_bible.md`, `characters.md`, `naming_table.md`, `plot_outline.md`, `timeline.md`, `theme.md`, `writing_guidelines.md`, `authors/{id}.json`)은 모두 **사람이 직접 채워야 하는 빈 템플릿** 상태다.
현재 `POST /works`는 디렉토리·빈 파일만 만든다 → 결과적으로 "신규 작품을 만드는 시스템"은 없는 거나 마찬가지.

**v0.2는 이 빈 구간을 채운다.** 컨셉 한 줄 + (선택) 추가 정보 → 회차 파이프라인이 즉시 진입 가능한 사전 자산 + 100화 아웃라인까지 자동 생성.

---

## 2. 사용자 흐름 (목표 시나리오)

```
1. 사용자: "F급 짐꾼이 시스템 버그를 발견해 S급으로 각성하는 헌터물,
            다크코미디 톤, 100화 완결, 주인공 강이준."
2. 시스템: 작품 컨셉 정리 → 사용자 확인 (문장 다듬기·추가 정보 받기)
3. 시스템: 엔딩 1줄 + 3막 구조 제안 → 사용자 확인 (잠금)
4. 시스템: 100화 줄거리 일괄 생성 (3막 × 33/34/33화) → 검수 → 사용자 확인
5. 시스템: 작품 제목 후보 5개 + 회차별 가제 100개 → 사용자 선택
6. 시스템: 각 화 앞뒤 줄거리 정합 검수 (i-1 끝 ↔ i 시작 ↔ i+1 진입)
7. 시스템: 전체 줄거리 검토 (3막 흐름·복선 회수·아크 무결성) → 자동 수정
8. 시스템: world_bible / characters / naming_table / timeline / theme /
            writing_guidelines / authors/{id}.json 생성
9. 시스템: chapter_outlines/ch001~ch100.yaml 생성 (overall + beats[3])
10. 출력: ch001 회차 파이프라인 진입 가능 상태 ✅
```

각 단계는 **승인 게이트**를 가짐 — 자동 진행 모드(`--auto`)와 단계 검토 모드(기본) 모두 지원.

---

## 3. 메타 파이프라인 — LangGraph 설계

```
init_concept            ← 사용자 입력 정규화 (logline + 옵션)
   ↓
ending_lock             ← 엔딩 1줄 + 3막 골격 생성
   ↓ ────────[ending_lock 검수자]──── revise loop (max 3)
plot_skeleton           ← 100화 overall 줄거리 일괄 생성 (막당 33/34/33화)
   ↓ ────────[outline_consistency 검수자]──── revise loop
   ↓ ────────[ending_lock 재검수]──── 100화 끝이 엔딩과 일치?
title_naming            ← 작품 제목 5개 + 회차별 가제 100개
   ↓
chapter_continuity      ← 화별 i-1↔i↔i+1 정합 검수 (sliding window)
   ↓
plot_review_full        ← 3막 흐름·복선·아크 (Map-Reduce: 막별 요약 → 통합)
   ↓
worldbuilding_gen       ← world_bible / theme 생성
   ↓
character_gen           ← characters / naming_table 생성
   ↓ ────────[character 검수자(기존)]──── 정의 vs 등장 일치?
timeline_gen            ← timeline.md 생성
   ↓
guidelines_gen          ← writing_guidelines.md 생성 (호명·반복 임계값 자동 산정)
   ↓
persona_gen             ← authors/{id}.json 페르소나 생성
   ↓
outlines_gen            ← chapter_outlines/ch001~ch100.yaml (overall + beats[3])
   ↓ ────────[direction 검수자(기존)]──── 비트가 overall을 충실히 담는가?
finalize                ← meta.json 갱신 (author_id, total_planned=100)
   ↓
END (회차 파이프라인 진입 가능 상태)
```

각 노드 실패 시: `meta_alert_and_halt` → `logs/failures/meta_*.json` + 텔레그램.

---

## 4. 검수자 — 기존 재사용 + 신규 3종

### 4.1 재사용 (기존 `ReviewerAgent` 그대로)

| 역할 | 기존 용도 | 메타에서 용도 |
|---|---|---|
| `direction` | 회차 비트 이행 검수 | `outlines_gen` 후 — 비트가 overall 줄거리를 담는지 |
| `character` | 회차 캐릭터 일관성 | `character_gen` 후 — 정의된 캐릭터와 등장 묘사 일치 |
| `quality` | 회차 문장 품질 | (메타에선 미사용 — 산문이 아니므로) |
| `repetition` | 회차 반복 패턴 | (메타에선 미사용) |

### 4.2 신규 3종 (`backend/app/teams/reviewer/meta_*.py`)

| 검수자 | 검수 대상 | 통과 기준 |
|---|---|---|
| `outline_consistency` | world_bible ↔ characters ↔ plot_outline ↔ 100화 줄거리 모순 | 점수 ≥ 8, 모순 0건 |
| `chapter_continuity` | ch_i-1 끝 ↔ ch_i 시작 ↔ ch_i+1 진입 정합 (sliding window) | 끊김·중복·모순 0건 |
| `ending_lock` | 엔딩 1줄 ↔ 100화 마지막 비트 일치 + 막별 클라이맥스 도달 | 막별 클라이맥스 도달 ✅, 엔딩 일치 ✅ |

세 검수자 모두 **기존 `ReviewerAgent` 패턴을 따른다**:
- 프롬프트는 `prompts.py`에 추가
- 점수(1~10) + 통과 여부 + 사유 + feedback 반환
- 실패 시 해당 노드의 writer 격(genenerator)이 `revise()` 호출
- max_retries 동일 (3회)

---

## 5. 데이터 — 입력/출력 스키마

### 5.1 입력 (사용자)

```yaml
# scripts/init_work.py --input concept.yaml 또는 API body
logline: "F급 짐꾼이 시스템 버그를 발견해 S급으로 각성"   # 필수
genre: "헌터물"                                          # 선택, 기본 "modern_fantasy"
mood: "다크코미디"                                        # 선택
total_chapters: 100                                       # 선택, 기본 100
protagonist: "강이준"                                      # 선택
keywords: ["시스템물", "각성물", "복수극"]                  # 선택
forbidden: ["성적 묘사", "실명 거론"]                      # 선택
reference_tone: "기존 modern_fantasy_game_01과 유사"       # 선택
work_id: null    # null이면 logline에서 자동 생성, 사용자 지정 가능
```

### 5.2 출력 (자동 생성)

`POST /works` 후 디렉토리는 동일하지만 **모든 파일이 의미 있는 내용으로 채워짐**:

```
novels/{work_id}/
├── meta.json              author_id, total_planned=100, ending_summary
├── theme.md               테마·약속·금지 요소 (3~5줄)
├── world_bible.md         시스템 메커니즘, 등급 체계, 던전 규칙 등
├── characters.md          주조연 5~8명 (이름·등급·성격·관계·아크)
├── naming_table.md        호칭표 (캐릭터 간 누가 누구를 뭐라 부르는지)
├── plot_outline.md        3막 구조 + 막별 주요 사건
├── timeline.md            전체 사건 연표
├── writing_guidelines.md  호명 임계값·반복 한계·문체 규칙
├── memory/                (빈 상태로 시작)
├── chapter_outlines/
│   ├── ch001.yaml         overall + beats[3] (각 비트 instruction 1,800자+)
│   ├── ...
│   └── ch100.yaml
└── chapters/              (비어있음, 회차 파이프라인이 채움)

authors/{author_id}.json   페르소나 (name, voice, strengths, taboos, model_override)
```

`chapter_outlines/ch_n.yaml`은 **기존 modern_fantasy_game_01과 100% 동일한 포맷**(overall + beats 리스트). 회차 파이프라인이 이걸 그대로 먹는다.

---

## 6. 인터페이스 — 3종 모두 지원

### 6.1 CLI: `scripts/init_work.py`

```bash
# 컨셉 yaml에서 전 자동
.venv/bin/python scripts/init_work.py --input concept.yaml --auto

# 단계별 검토 (기본)
.venv/bin/python scripts/init_work.py --logline "..." --total 100

# 단계 재실행 (실패 노드부터)
.venv/bin/python scripts/init_work.py --resume {work_id} --from plot_skeleton

# dry-run (LLM 호출 없이 디렉토리·스키마만 검증)
.venv/bin/python scripts/init_work.py --logline "..." --dry-run
```

### 6.2 API: 강화된 `/works`

```
POST /works
Body: { logline, genre?, mood?, total?, protagonist?, ... }
→ 작품 생성 시작 (background task), task_id 반환

GET  /works/{work_id}/init/status        ← 진행 단계, 검수 결과
GET  /works/{work_id}/init/preview/{step}  ← 단계 결과 미리보기
POST /works/{work_id}/init/approve/{step}  ← 단계 승인 (다음 단계로)
POST /works/{work_id}/init/regenerate/{step}  ← 단계 재실행
POST /works/{work_id}/init/edit/{step}    ← 사용자 직접 편집
```

### 6.3 Admin UI: `/admin/new` 마법사

단계별 페이지 + 좌측 진행 트래커:

```
[1] 컨셉      [2] 엔딩      [3] 줄거리 100화
[4] 제목/가제 [5] 정합      [6] 검토      [7] 사전자산
[8] 아웃라인  [9] 완료
```

각 단계 우측: AI 결과 + 재생성 / 직접 편집 / 다음 단계 버튼.

---

## 7. 마일스톤 — 4 스프린트

| 스프린트 | 범위 | 산출물 |
|---|---|---|
| **M1 — 골격** | 메타 그래프 + ending_lock + plot_skeleton (100화 overall만) | `scripts/init_work.py` 으로 100화 overall 자동 생성, 사람이 검토 |
| **M2 — 검수** | 신규 검수자 3종 + chapter_continuity sliding window + plot_review_full | 화별 정합·복선 회수 자동 검수, revise 루프 동작 |
| **M3 — 자산** | worldbuilding/character/timeline/guidelines/persona/outlines 노드 + 기존 검수자 재사용 | `chapter_outlines/ch001~ch100.yaml` 100% 자동, 회차 파이프라인 즉시 진입 가능 |
| **M4 — UX** | API 엔드포인트 + Admin UI 마법사 | 웹에서 클릭만으로 신규 작품 → ch001 발행까지 |

각 스프린트 종료 조건:
- M1: logline 1줄 → 100화 overall yaml 생성, 사람 검토 통과
- M2: 검수자 3종이 모두 모순 케이스 1건 이상 잡아냄 (테스트 케이스 포함)
- M3: **새 작품 1개 생성 → ch001~ch003까지 회차 파이프라인이 무수정 통과** (성공 기준)
- M4: 비개발자가 Admin UI만으로 작품 생성 + ch001 발행

---

## 8. 성공 기준

1. 사용자 입력 = logline 1줄. 그 외 모두 옵션.
2. 사람 개입 없이(또는 단계 검토 1회씩) 회차 파이프라인 진입 가능 상태에 도달한다.
3. 새 작품의 ch001~ch003가 기존 회차 파이프라인의 **검수 4종을 무수정 통과**한다 (= 사전 자산이 충분히 자체정합).
4. 100화 줄거리 ↔ 엔딩 ↔ 막별 클라이맥스가 일관된다 (`ending_lock` 검수자 통과).
5. M3 종료 시점, modern_fantasy_game_01과 **동일 포맷**의 새 작품 디렉토리가 1개 이상 생성되어 있다.

---

## 9. 리스크 / 오픈 이슈

| 리스크 | 대응 |
|---|---|
| gemma4:e2b 짧은 컨텍스트 — 100화 일괄 생성 시 출력 잘림 | 막 단위(33+34+33) 분할 생성, 화별 overall 200~300자로 제한 |
| LLM 환각 — world_bible과 plot_outline 모순 | `outline_consistency` 검수자 + 단계 게이트 |
| chapter_continuity sliding window — 100화 × 3 = 300회 LLM 호출 비용 | regex pre-check (캐릭터·시간·장소 키워드 흐름) → 의심 구간만 LLM |
| 페르소나 자동 생성의 톤 일관성 | `reference_tone` 옵션으로 기존 작가 페르소나 모방 |
| 사용자가 단계 중 마음 바꿈 (예: 엔딩 변경) | `--from` 재실행 + downstream 자동 무효화 |

---

## 10. 결정 필요 (사용자 승인 사항)

- [ ] **단계 게이트 기본값**: 단계 검토(기본) vs 전 자동(`--auto`). 추천: 단계 검토.
- [ ] **회차 수 기본값**: 100화 (메모리 규칙 따름).
- [ ] **엔딩 잠금 시점**: M1에서부터(추천) vs M3 마지막에 자동 도출.
- [ ] **신규 작가 페르소나**: 매 작품마다 새 페르소나 자동 생성 vs 기존 페르소나 풀에서 선택.
- [ ] **API/CLI/UI 우선순위**: M1~M3는 CLI 우선, M4에서 API+UI(추천) vs 처음부터 셋 다 병행.

---

## 11. 회차 파이프라인 → 메타 파이프라인 진입점 다이어그램

```
사용자 logline
    ↓
[메타 파이프라인 (이번 PRD 범위)]
    ↓
novels/{work_id}/* 자산 + chapter_outlines/ch001~100.yaml
    ↓
scripts/run_chapters_1_to_10.py {work_id}
    ↓
[회차 파이프라인 (graph.py — 이미 완성)]
    ↓
chapters/ch_n.md + _meta.json + _summary.md
    ↓
텔레그램 발행
```
