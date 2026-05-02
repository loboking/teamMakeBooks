"""발행팀 프롬프트 — 제목/태그/한줄요약 생성."""
from __future__ import annotations

PUBLISH_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 5},
        "one_line_summary": {"type": "string"},
    },
    "required": ["title", "tags", "one_line_summary"],
}


def build_publisher_prompt(ctx, draft: str) -> str:
    return (
        f"[작품 정보]\n장르: {ctx.work_id}\n회차: {ctx.current_chapter_n}\n\n"
        f"[본문]\n{draft.strip()}\n\n"
        f"[지시]\n다음 JSON 스키마로 발행 메타데이터를 생성:\n"
        f'{{"title": "회차 제목 (15자 이내, 흡입력 있게)", '
        f'"tags": ["태그1","태그2","태그3","태그4","태그5" — 3~5개], '
        f'"one_line_summary": "한국 웹소설 한 줄 요약 (50자 이내, 다음 화 보고 싶게)"}}\n'
        f"본문 분위기와 핵심 사건을 반영. 다른 텍스트 절대 금지.\n\n"
        f"[학습 예시]\n"
        f'{{"title":"각성, 그리고 오류","tags":["헌터물","시스템","각성","현대판타지","약자성장"],'
        f'"one_line_summary":"만년 F급 짐꾼이 던전 추락 끝에 시스템을 만난다."}}'
    )
