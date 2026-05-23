---
type: system_doc
---

# 위키 구조·규칙

## 디렉토리 구조 (작품별 동일)

```
wiki/{work_id}/
├── _작품인덱스.md      ← 작품 메타 + 회차 진척 + 주요 인물 링크
├── characters/         ← 인물별 누적 상태
│   └── {이름}.md
├── events/             ← 회차별 사건 단위
│   └── ch{n:03d}_{slug}.md
├── threads/            ← 떡밥 (open/closed)
│   └── {떡밥명}.md
├── locations/          ← 공간·조직
│   └── {장소}.md
└── timeline.md         ← 회차별 사건 한 줄 시퀀스
```

## 파일별 frontmatter 스키마

### `characters/{이름}.md`
```yaml
---
type: character
work_id: {wid}
role: 주인공|조력자|적대자|조연
status: active|deceased|missing|inactive
first_appeared: ch{n}
last_appeared: ch{n}
limit_full: 5         # 회차당 풀네임 한도 (검수자가 사용)
limit_short: 35       # 회차당 짧은 이름 한도
short_name: 하린       # 짧은 이름 (서술 회전용)
related: ["[[마린]]"]  # wikilink 관계
threads: ["[[포탈의 정체]]"]
---

## 정의 (불변)
- 등급/직업/외모/성격/Arc

## 누적 상태 (회차별 자동 추가)
- ch001: <한 줄 요약>
- ch002: <한 줄 요약>
```

### `events/ch{n:03d}_{slug}.md`
```yaml
---
type: event
work_id: {wid}
chapter_n: {n}
characters: ["[[차하린]]", "[[마린]]"]
locations: ["[[학교 도서관]]", "[[이계 마을]]"]
threads_affected: ["[[포탈의 정체]]"]
---

## 사건 요약
<3~5줄>
```

### `threads/{떡밥}.md`
```yaml
---
type: thread
work_id: {wid}
status: open|closed
introduced_ch: {n}
resolved_ch: {n}        # closed일 때만
related_characters: ["[[좌선장]]"]
---

## 떡밥 내용
<무엇이 미해결인지>

## 진행 이력
- ch{n}: <한 줄>
```

### `locations/{장소}.md`
```yaml
---
type: location
work_id: {wid}
appears_in: [ch001, ch002, ...]
---

## 설명
<공간·조직 디테일>
```

## 자동 갱신 규칙

회차 발행 후 시스템이 자동:
1. 등장 인물 각각의 `characters/{이름}.md` 의 **누적 상태** 섹션에 "- ch{n}: <요약>" 추가
2. `events/ch{n:03d}_{slug}.md` 새 파일
3. 떡밥 회수 시 `threads/{떡밥}.md` 의 `status: open → closed`, `resolved_ch: {n}`
4. `timeline.md` 마지막에 "- ch{n}: <한 줄>" 추가

## 회차 작성 전 쿼리

writer 진입 시 wiki에서:
- 등장 예정 인물의 `characters/*.md`
- `status: open` 떡밥 전부
- 직전 N화의 `events/*.md`
- 사용 장소의 `locations/*.md`

발췌해 LLM 컨텍스트에 주입.
