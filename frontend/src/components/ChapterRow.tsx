import Link from "next/link";
import type { ChapterSummary } from "@/lib/data";

type Props = {
  chapter: ChapterSummary;
  workId: string;
};

function formatDate(iso: string): string {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, "0")}.${String(d.getDate()).padStart(2, "0")}`;
  } catch {
    return "";
  }
}

export default function ChapterRow({ chapter, workId }: Props) {
  return (
    <Link
      href={`/works/${workId}/chapters/${chapter.n}`}
      className="flex flex-col gap-1.5 py-4 px-4 border-b border-[var(--border)] hover:bg-[var(--bg-chip)] transition-colors duration-150 active:bg-[var(--bg-chip)]"
    >
      <div className="flex items-start justify-between gap-2">
        <span className="font-medium text-[var(--text-primary)] leading-snug">
          <span className="text-[var(--text-muted)] text-sm mr-1.5">
            {chapter.n}화
          </span>
          {chapter.title}
        </span>
        <span className="text-xs text-[var(--text-muted)] shrink-0">
          {formatDate(chapter.publishedAt)}
        </span>
      </div>

      {chapter.oneLineSummary && (
        <p className="text-sm text-[var(--text-secondary)] leading-relaxed line-clamp-2">
          {chapter.oneLineSummary}
        </p>
      )}

      {chapter.tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-0.5">
          {chapter.tags.slice(0, 4).map((tag) => (
            <span
              key={tag}
              className="text-xs px-2 py-0.5 rounded-full bg-[var(--bg-chip)] text-[var(--text-muted)] border border-[var(--border)]"
            >
              {tag}
            </span>
          ))}
        </div>
      )}
    </Link>
  );
}
