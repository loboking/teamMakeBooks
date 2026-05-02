import { notFound } from "next/navigation";
import Link from "next/link";
import { getWork, listChapters, listWorks } from "@/lib/data";
import AiBadge from "@/components/AiBadge";
import AiPersonaLabel from "@/components/AiPersonaLabel";
import ChapterRow from "@/components/ChapterRow";
import DarkModeToggle from "@/components/DarkModeToggle";

export function generateStaticParams() {
  return listWorks().map((w) => ({ work_id: w.workId }));
}

const GENRE_LABELS: Record<string, string> = {
  modern_fantasy_game: "현대판타지",
  romance: "로맨스",
  thriller: "스릴러",
};

const COVER_GRADIENTS = [
  "from-indigo-900 via-violet-900 to-slate-900",
  "from-slate-900 via-indigo-900 to-violet-900",
  "from-violet-900 via-slate-900 to-indigo-900",
];

function coverGradient(workId: string): string {
  return COVER_GRADIENTS[workId.length % COVER_GRADIENTS.length];
}

export default async function WorkDetailPage({
  params,
}: {
  params: Promise<{ work_id: string }>;
}) {
  const { work_id } = await params;
  const work = getWork(work_id);
  if (!work) notFound();

  const chapters = listChapters(work_id);

  return (
    <div className="max-w-[480px] mx-auto min-h-screen flex flex-col">
      {/* Header */}
      <header className="sticky top-0 z-10 bg-[var(--bg-base)] border-b border-[var(--border)] px-4 py-3 flex items-center gap-3">
        <Link
          href="/"
          aria-label="홈으로"
          className="w-8 h-8 flex items-center justify-center rounded-lg text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-chip)] transition-colors"
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
        <h1 className="flex-1 text-sm font-semibold text-[var(--text-primary)] line-clamp-1">
          {work.title}
        </h1>
        <DarkModeToggle />
      </header>

      <main className="flex-1">
        {/* Cover */}
        <div
          className={`h-56 bg-gradient-to-br ${coverGradient(work_id)} flex flex-col items-start justify-end p-6`}
        >
          <div className="flex gap-2 mb-3">
            <span className="text-xs px-2 py-0.5 rounded-md bg-white/10 text-white/80 border border-white/20">
              {GENRE_LABELS[work.genre] ?? work.genre}
            </span>
            {work.isAiPersona && <AiBadge size="sm" />}
          </div>
          <h2 className="text-2xl font-bold text-white leading-snug">
            {work.title}
          </h2>
        </div>

        {/* Meta */}
        <div className="px-4 py-5 border-b border-[var(--border)] space-y-4">
          {/* Author card */}
          <div className="rounded-xl bg-[var(--bg-card)] border border-[var(--border)] p-4 space-y-1">
            <div className="flex items-center gap-2">
              <span className="font-semibold text-[var(--text-primary)]">
                {work.author.name}
              </span>
              {work.isAiPersona && <AiPersonaLabel />}
            </div>
            {work.author.style && (
              <p className="text-sm text-[var(--text-secondary)]">
                {work.author.style}
              </p>
            )}
          </div>

          {/* Stats row */}
          <div className="flex gap-4 text-sm text-[var(--text-secondary)]">
            <span>전체 {work.publishedChapters}화</span>
            <span className="text-[var(--border)]">|</span>
            <span>{work.copyright}</span>
          </div>
        </div>

        {/* Chapter list */}
        <section>
          <div className="px-4 py-3 flex items-center justify-between border-b border-[var(--border)]">
            <h3 className="font-semibold text-[var(--text-primary)]">
              회차 목록
            </h3>
            <span className="text-xs text-[var(--text-muted)]">
              {chapters.length}화
            </span>
          </div>

          {chapters.length === 0 ? (
            <p className="px-4 py-10 text-center text-[var(--text-muted)] text-sm">
              발행된 회차가 없습니다.
            </p>
          ) : (
            <ul>
              {chapters.map((ch) => (
                <li key={ch.n}>
                  <ChapterRow chapter={ch} workId={work_id} />
                </li>
              ))}
            </ul>
          )}
        </section>
      </main>

      <footer className="px-4 py-6 text-center text-xs text-[var(--text-muted)] border-t border-[var(--border)]">
        {work.copyright}
      </footer>
    </div>
  );
}
