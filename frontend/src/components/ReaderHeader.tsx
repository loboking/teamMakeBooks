"use client";

import Link from "next/link";

type Props = {
  title: string;
  backHref: string;
  fontSize: number;
  onFontSizeChange: (size: number) => void;
};

const FONT_SIZES = [16, 18, 21] as const;
const FONT_LABELS = ["작게", "보통", "크게"] as const;

export default function ReaderHeader({
  title,
  backHref,
  fontSize,
  onFontSizeChange,
}: Props) {
  return (
    <header className="sticky top-0 z-10 bg-[var(--bg-base)] border-b border-[var(--border)] px-4 py-3 flex items-center gap-3">
      {/* Back */}
      <Link
        href={backHref}
        aria-label="뒤로가기"
        className="shrink-0 w-8 h-8 flex items-center justify-center rounded-lg text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-chip)] transition-colors"
      >
        <svg
          width="20"
          height="20"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M15 18l-6-6 6-6" />
        </svg>
      </Link>

      {/* Title */}
      <p className="flex-1 text-sm font-medium text-[var(--text-primary)] line-clamp-1">
        {title}
      </p>

      {/* Font size controls */}
      <div className="flex items-center gap-1 shrink-0">
        {FONT_SIZES.map((size, i) => (
          <button
            key={size}
            onClick={() => onFontSizeChange(size)}
            aria-label={`글자 크기 ${FONT_LABELS[i]}`}
            className={`px-2 py-1 text-xs rounded-md border transition-colors duration-150 ${
              fontSize === size
                ? "border-violet-500 bg-violet-900/30 text-violet-300"
                : "border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
            }`}
          >
            {FONT_LABELS[i]}
          </button>
        ))}
      </div>
    </header>
  );
}
