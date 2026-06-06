"""결정론적 중복 감지·제거 + 금지어 감소기.

LLM이 생성한 텍스트에서:
1. 거의 동일한 문단이 중복되면 뒤의 것 제거
2. 정확히 일치하는 문장이 2회 이상 등장하면 뒤의 것 제거
3. 동일 구문이 3회 이상 반복되면 2개까지만 남기고 나머지 제거
4. 금지어(미세하게 등)가 회차 한계를 초과하면 초과분 제거
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class DedupResult:
    original: str
    fixed: str
    removed_paragraphs: int
    removed_phrases: int
    removed_banned_words: int
    details: list[str]


def _normalize(text: str) -> str:
    """비교용 정규화 — 공백/어미/조사 차이 무시."""
    t = re.sub(r'\s+', '', text)
    # 조사 제거
    t = re.sub(r'[은는이가을를의]', '', t)
    # 어미 통일 (했다→하, 왔다→오, 갔다→가, 났다→나, etc.)
    t = re.sub(r'(했|왔|갔|났|봤|먹|움직|떨|닿|올라|내려)(다|었다|고|며|서)', '', t)
    # 마침표 제거
    t = re.sub(r'[.!?。，、]', '', t)
    return t


def _jaccard_similarity(a: str, b: str) -> float:
    """두 텍스트의 자카드 유사도 (n-gram 기반)."""
    na = _normalize(a)
    nb = _normalize(b)
    if not na or not nb:
        return 0.0
    # 4-gram 사용
    grams_a = set(na[i:i+4] for i in range(len(na) - 3))
    grams_b = set(nb[i:i+4] for i in range(len(nb) - 3))
    if not grams_a or not grams_b:
        return 0.0
    intersection = len(grams_a & grams_b)
    union = len(grams_a | grams_b)
    return intersection / union if union else 0.0


def _split_sentences(text: str) -> list[str]:
    """텍스트를 문장 단위로 분리. 대사·시스템창은 보호."""
    # 대사·시스템창 마스킹
    masked = text
    spans: list[tuple[str, str]] = []
    idx = 0
    changed = True
    while changed:
        changed = False
        for pat in [r'"[^"]*"', r'\[.*?\]']:
            m = re.search(pat, masked)
            if m:
                key = f"\x00S{idx}\x00"
                spans.append((key, m.group()))
                masked = masked[:m.start()] + key + masked[m.end():]
                idx += 1
                changed = True
                break

    # 마침표/물음표/느낌표 기준 분리 (한국어 온점 포함)
    sentences = re.split(r'(?<=[.!?。])\s+', masked)

    # 마스킹 복원
    for i, sent in enumerate(sentences):
        for key, original in spans:
            sent = sent.replace(key, original)
        sentences[i] = sent

    return sentences


# ── 금지어 감소기 ──────────────────────────────────────────────────────────────

# 부사/수식어: "미세하게 달라 보였다" → "달라 보였다" (삭제만)
_BANNED_ADVERBS: dict[str, int] = {
    "미세하게": 3,       # 3회까지 허용, 4회부터 삭제
    "미묘하게": 2,
}

# 추상 동사+보조동사: "계산을 시작했다", "불일치를 포착했다" — 문장 단위로 삭제
_BANNED_VERB_PHRASES: list[str] = [
    "불일치를 포착",
    "불일치를 감지",
    "불일치를 인식",
    "미세한 불일치",
    "이질적인",
    "물리적 흐름",
    "물리적 법칙",
    "존재론적",
    "에너지 흐름",
]


def _reduce_banned_words(text: str) -> tuple[str, int, list[str]]:
    """금지어 출현을 한계 이하로 축소. 삭제 방식.

    부사는 단순 삭제. 구문은 문장 전체 삭제.
    """
    result = text
    total_removed = 0
    details: list[str] = []

    # 1) 부사 감소: 대사 마스킹 후 치환
    masked = result
    dialogue_spans: list[tuple[str, str]] = []
    idx = 0
    changed = True
    while changed:
        changed = False
        for pat in [r'"[^"]*"', r'"[^"]*"', r'\[.*?\]']:
            m = re.search(pat, masked)
            if m:
                key = f"\x00BW{idx}\x00"
                dialogue_spans.append((key, m.group()))
                masked = masked[:m.start()] + key + masked[m.end():]
                idx += 1
                changed = True
                break

    for adverb, limit in _BANNED_ADVERBS.items():
        occurrences = list(re.finditer(re.escape(adverb), masked))
        if len(occurrences) <= limit:
            continue
        for occ in reversed(occurrences[limit:]):
            masked = masked[:occ.start()] + masked[occ.end():]
            total_removed += 1
            details.append(f"금지어 감소: '{adverb}' 제거 (한계 {limit}회 초과)")

    for key, original in dialogue_spans:
        masked = masked.replace(key, original)
    result = masked

    # 2) 금지 구문: 대사/시스템창 보호 후, 해당 문장 전체 삭제
    masked = result
    dialogue_spans = []
    idx = 0
    changed = True
    while changed:
        changed = False
        for pat in [r'"[^"]*"', r'"[^"]*"', r'\[.*?\]']:
            m = re.search(pat, masked)
            if m:
                key = f"\x00BP{idx}\x00"
                dialogue_spans.append((key, m.group()))
                masked = masked[:m.start()] + key + masked[m.end():]
                idx += 1
                changed = True
                break

    for phrase in _BANNED_VERB_PHRASES:
        # 해당 구문을 포함하는 문장을 찾아 삭제
        lines = masked.split("\n")
        new_lines: list[str] = []
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith(">"):
                new_lines.append(line)
                continue
            if phrase in stripped:
                total_removed += 1
                details.append(f"금지구문 삭제: '{stripped[:50]}...' ({phrase})")
                continue
            new_lines.append(line)
        masked = "\n".join(new_lines)

    for key, original in dialogue_spans:
        masked = masked.replace(key, original)
    result = masked

    return result, total_removed, details


def remove_duplicates(
    draft: str,
    *,
    paragraph_threshold: float = 0.5,
    sentence_threshold: float = 0.45,
    phrase_min_length: int = 15,
    phrase_max_occurrences: int = 2,
) -> DedupResult:
    """중복 문단·문장·반복 구문을 제거.

    Parameters
    ----------
    draft : str
        검사할 본문
    paragraph_threshold : float
        문단 중복 판정 유사도 (0~1)
    sentence_threshold : float
        문장 중복 판정 유사도 (0~1)
    phrase_min_length : int
        반복 구문 최소 길이 (문자 수)
    phrase_max_occurrences : int
        동일 구문 허용 최대 등장 횟수
    """
    paragraphs = draft.split("\n")
    kept: list[str] = []
    seen_normalized: list[tuple[str, str]] = []  # (정규화, 원본)
    removed_paras = 0
    details: list[str] = []

    # ── Phase 1: 문단 중복 제거 ──
    for para in paragraphs:
        stripped = para.strip()
        if not stripped:
            kept.append(para)
            continue

        # 대사만 있는 줄은 중복 검사 스킵
        if stripped.startswith('"') or stripped.startswith('"'):
            kept.append(para)
            seen_normalized.append((_normalize(stripped), stripped))
            continue

        # 시스템 메시지도 스킵
        if stripped.startswith('[') and stripped.endswith(']'):
            kept.append(para)
            seen_normalized.append((_normalize(stripped), stripped))
            continue

        is_dup = False
        for prev_norm, prev_orig in seen_normalized:
            sim = _jaccard_similarity(stripped, prev_orig)
            if sim >= paragraph_threshold:
                is_dup = True
                details.append(
                    f"문단 중복 제거 (유사도 {sim:.0%}): "
                    f"'{stripped[:40]}...' ≈ '{prev_orig[:40]}...'"
                )
                break

        if is_dup:
            removed_paras += 1
        else:
            kept.append(para)
            seen_normalized.append((_normalize(stripped), stripped))

    result = "\n".join(kept)

    # ── Phase 1.5: 문장 단위 중복 제거 ──
    # 한 줄에 여러 문장이 있는 경우 문단 비교로 잡히지 않음
    # 줄 구조를 보존하면서 한 줄 내의 중복 문장만 제거
    seen_sents: list[str] = []
    fixed_lines: list[str] = []

    for para in paragraphs:
        para_stripped = para.strip()
        # 빈 줄, 대사 전용 줄, 시스템 메시지는 그대로 유지
        if not para_stripped or para_stripped.startswith('"') or para_stripped.startswith('"'):
            fixed_lines.append(para)
            continue
        if para_stripped.startswith('[') and para_stripped.endswith(']'):
            fixed_lines.append(para)
            continue
        # 한 줄에 문장이 1개뿐이면 그대로
        sents = _split_sentences(para_stripped)
        if len(sents) <= 1:
            seen_sents.append(para_stripped)
            fixed_lines.append(para)
            continue

        # 다중 문장 줄: 중복 문장만 필터링
        kept_sents_in_line: list[str] = []
        for sent in sents:
            is_dup = False
            for prev in seen_sents:
                sim = _jaccard_similarity(sent.strip(), prev.strip())
                if sim >= sentence_threshold:
                    is_dup = True
                    details.append(
                        f"문장 중복 제거 (유사도 {sim:.0%}): "
                        f"'{sent.strip()[:50]}...'"
                    )
                    break
            if not is_dup:
                seen_sents.append(sent.strip())
                kept_sents_in_line.append(sent)
            else:
                removed_paras += 1  # 문장 제거 카운트 재사용

        # 남은 문장들을 원래 줄 형태로 재조합
        if kept_sents_in_line:
            # 원래 줄의 들여쓰기/형태를 최대한 보존
            indent = re.match(r'^(\s*)', para)
            prefix = indent.group(1) if indent else ""
            fixed_lines.append(prefix + " ".join(kept_sents_in_line))
        # 전부 제거된 경우 줄 자체를 생략

    result = "\n".join(fixed_lines)

    # ── Phase 2: 긴 구문 반복 제거 ──
    # 공백 정규화 후 동일 문장 패턴 탐지
    phrases_removed = 0
    # 마스킹: 대사·시스템창 보호
    masked = result
    dialogue_spans: list[tuple[str, str]] = []
    idx = 0
    changed = True
    while changed:
        changed = False
        for pat in [r'"[^"]*"', r'"[^"]*"', r'\[.*?\]']:
            m = re.search(pat, masked)
            if m:
                key = f"\x00P{idx}\x00"
                dialogue_spans.append((key, m.group()))
                masked = masked[:m.start()] + key + masked[m.end():]
                idx += 1
                changed = True
                break

    # 문장 단위로 분리
    sentences = re.split(r'(?<=[.!?。])\s+', masked)
    phrase_counts: dict[str, list[int]] = {}

    for i, sent in enumerate(sentences):
        sent_norm = _normalize(sent)
        if len(sent_norm) < phrase_min_length:
            continue
        phrase_counts.setdefault(sent_norm, []).append(i)

    # 3회 이상 등장한 구문 → 처음 N개만 유지
    remove_indices: set[int] = set()
    for norm, indices in phrase_counts.items():
        if len(indices) > phrase_max_occurrences:
            for idx_to_remove in indices[phrase_max_occurrences:]:
                remove_indices.add(idx_to_remove)
                phrases_removed += 1
                orig = sentences[idx_to_remove]
                details.append(f"구문 반복 제거: '{orig[:50]}...'")

    if remove_indices:
        kept_sentences = [s for i, s in enumerate(sentences) if i not in remove_indices]
        masked = " ".join(kept_sentences)

    # 대사 복원
    for key, original in dialogue_spans:
        masked = masked.replace(key, original)

    if phrases_removed > 0 or removed_paras > 0:
        result = masked

    # ── Phase 3.5: 정확히 일치하는 문장 중복 제거 (줄 단위)
    #    "오늘 아침은 이걸로 할게요"가 두 줄에 걸쳐 중복되는 버그를 잡는다.
    line_seen: dict[str, str] = {}  # 정규화 → 원본
    dup_lines: list[str] = []
    out_lines: list[str] = []
    for line in result.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith(">"):
            out_lines.append(line)
            continue
        norm = _normalize(stripped)
        if norm in line_seen:
            dup_lines.append(stripped)
            removed_paras += 1
            details.append(f"문장 중복(정확히 일치): '{stripped[:50]}...'")
        else:
            line_seen[norm] = stripped
            out_lines.append(line)
    if dup_lines:
        result = "\n".join(out_lines)

    # ── Phase 4: 금지어 감소
    result, banned_removed, banned_details = _reduce_banned_words(result)
    details.extend(banned_details)

    return DedupResult(
        original=draft,
        fixed=result,
        removed_paragraphs=removed_paras,
        removed_phrases=phrases_removed,
        removed_banned_words=banned_removed,
        details=details,
    )
