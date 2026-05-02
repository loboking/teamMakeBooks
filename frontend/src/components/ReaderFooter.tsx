import Link from "next/link";

type Props = {
  workId: string;
  currentN: number;
  totalN: number;
};

export default function ReaderFooter({ workId, currentN, totalN }: Props) {
  const hasPrev = currentN > 1;
  const hasNext = currentN < totalN;

  const navLinkClass =
    "flex-1 flex items-center justify-center gap-1.5 py-3 text-sm font-medium rounded-lg border border-[var(--border)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:border-violet-500/60 transition-colors duration-200 disabled:opacity-30";

  return (
    <footer className="border-t border-[var(--border)] bg-[var(--bg-base)] px-4 py-4 flex gap-2">
      {hasPrev ? (
        <Link
          href={`/works/${workId}/chapters/${currentN - 1}`}
          className={navLinkClass}
        >
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M15 18l-6-6 6-6" />
          </svg>
          이전화
        </Link>
      ) : (
        <span className={`${navLinkClass} opacity-30 cursor-not-allowed`}>
          이전화
        </span>
      )}

      <Link
        href={`/works/${workId}`}
        className="flex-1 flex items-center justify-center py-3 text-sm font-medium rounded-lg border border-[var(--border)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:border-violet-500/60 transition-colors duration-200"
      >
        목록
      </Link>

      {hasNext ? (
        <Link
          href={`/works/${workId}/chapters/${currentN + 1}`}
          className={navLinkClass}
        >
          다음화
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M9 18l6-6-6-6" />
          </svg>
        </Link>
      ) : (
        <span className={`${navLinkClass} opacity-30 cursor-not-allowed`}>
          다음화
        </span>
      )}
    </footer>
  );
}
