# 휴먼 개입 가이드

> 작가/검수/발행 자동 파이프라인이 실패한 회차를 사람이 처리하는 절차.
> 실패는 `logs/failures/` 에 JSON으로 누적. 패턴은 `scripts/failures_report.py` 로 분석.

---

## 1. 실패 발견 경로

| 경로 | 설명 |
|---|---|
| 텔레그램 경보 | 검수 max_retry 소진 시 자동 전송 |
| `logs/alerts.log` | append-only 텍스트 로그 |
| `logs/failures/<ts>_ch<n>_<stage>.json` | 구조화된 실패 케이스 (사람 분석용) |
| `python scripts/failures_report.py` | 최근 N일 실패 패턴 요약 |

---

## 2. 실패 케이스 정기 점검

매일 또는 매주 한 번:

```bash
python scripts/failures_report.py --since 7
```

출력 예시:
```
📊 실패 리포트 — 최근 7일
총 실패 건수: 4

【단계별 실패】
  quality      3건
  naming       1건

【회차별 실패 (Top 10)】
  ch003  2건
  ch010  1건
  ...

【⚠️ 반복 실패 회차 (≥3회) — 룰 조정 신호】
  ch003  3건  단계분포: {'quality': 3}
```

→ **단계 한 곳에 집중되면 그 검수 룰이 너무 엄격하다는 신호.**

---

## 3. 개입 옵션 4가지

### 옵션 A — 단순 재시도 (변경 없이)

```bash
.venv/bin/python scripts/run_poc_chapter.py \
    --work-id modern_fantasy_game_01 --chapter 3
```

LLM 비결정성으로 다시 시도하면 통과할 수도 있음. 1회만 시도하고 다음 옵션 고려.

### 옵션 B — 검수 임계 완화 후 재시도

`backend/app/teams/reviewer/prompts.py` 의 quality reviewer instruction에서 임계값 조정:

- 평균 문장 길이 미만 임계: 20 → 18
- 단문 회차 초과 임계: 10 → 14
- 풀네임 초과 임계: 5 → 7

수정 후 재시도. 단 임계 너무 풀면 모든 회차 품질 떨어짐 — 신중히.

### 옵션 C — chapter_outline 손보기

`novels/<work>/chapter_outlines/ch<n>.yaml` 의 비트 instruction을 더 구체적으로 수정.
"비트 1: 1,800자 이상" 같은 강한 분량 요구가 모델 한계와 충돌하면 1,500자로 완화.

### 옵션 D — 본문 직접 편집 + 발행 처리

작가 모델이 도저히 못 만들면 사람이 직접 편집:

1. 실패 회차의 draft 부분을 `logs/failures/<ts>_ch<n>_*.json` 의 `draft_snippet_head/tail`에서 확인 (본문 전체는 stdout 로그 참조).
2. `novels/<work>/chapters/ch<n>.md` 파일을 사람이 직접 편집.
3. 메타 파일 작성:
   ```bash
   cat > novels/<work>/chapters/ch<n>_meta.json <<EOF
   {
     "chapter_n": <n>,
     "title": "...",
     "tags": ["..."],
     "one_line_summary": "...",
     "published_at": "$(date -u +%Y-%m-%dT%H:%M:%S+00:00)",
     "ai_badge": false,
     "human_edited": true
   }
   EOF
   ```
4. `novels/<work>/meta.json` 의 `published_chapters` 카운터 갱신.
5. git commit + push → GitHub Actions 자동 배포.

---

## 4. 룰 조정 의사 결정 흐름

```
실패 보고서 확인
    ↓
같은 단계 3회 이상 반복?  ── No → 옵션 A (단순 재시도)
    ↓ Yes
임계 수치 문제로 보임?     ── Yes → 옵션 B (임계 완화)
    ↓ No
chapter_outline 분량 강제 ── Yes → 옵션 C (outline 완화)
    ↓ No
모델 능력 한계             → 옵션 D (사람 편집)
```

---

## 5. 정기 작업 권장 (cron)

```cron
# 매일 09:00 실패 리포트 텔레그램 자동 전송
0 9 * * * /Volumes/SSD2T/teamMakeBooks/.venv/bin/python /Volumes/SSD2T/teamMakeBooks/scripts/failures_report.py --since 1 > /tmp/daily_failures.txt && curl -s -X POST "https://api.telegram.org/bot<TOKEN>/sendMessage" -d "chat_id=<CHAT>" --data-urlencode "text=$(cat /tmp/daily_failures.txt)"
```

---

## 6. 참고 — 실패 기록 파일 구조

`logs/failures/<ts>_ch<n>_<stage>.json`:

```json
{
  "work_id": "modern_fantasy_game_01",
  "chapter_n": 3,
  "failure_stage": "quality",
  "failure_reason": "단편 문장 나열 및 단조로운 호흡...",
  "started_at": "2026-05-02T...",
  "failed_at": "2026-05-02T...",
  "max_retries": 3,
  "review_history": [
    {"role": "naming", "attempt": 1, "passed": true, ...},
    {"role": "direction", "attempt": 1, "passed": true, ...},
    {"role": "quality", "attempt": 1, "passed": false, "feedback": "..."},
    {"role": "quality", "attempt": 2, "passed": false, "feedback": "..."},
    {"role": "quality", "attempt": 3, "passed": false, "feedback": "..."}
  ],
  "draft_chars": 4621,
  "draft_snippet_head": "강이준은 ...",
  "draft_snippet_tail": "...어둠 속에서 무언가가 다가왔다."
}
```
