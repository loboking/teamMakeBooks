import { listWorks, getWork } from "@/lib/data";
import WorkCard from "@/components/WorkCard";
import DarkModeToggle from "@/components/DarkModeToggle";

export default function HomePage() {
  const works = listWorks();
  const worksWithAuthor = works.map((w) => {
    const detail = getWork(w.workId);
    return { work: w, authorName: detail?.author.name ?? w.authorId };
  });

  return (
    <div className="max-w-[480px] mx-auto min-h-screen flex flex-col">
      {/* Header */}
      <header className="sticky top-0 z-10 bg-[var(--bg-base)] border-b border-[var(--border)] px-4 py-3 flex items-center justify-between">
        <h1 className="font-bold text-lg text-[var(--text-primary)] tracking-tight">
          teamMakeBooks
        </h1>
        <DarkModeToggle />
      </header>

      {/* Work list */}
      <main className="flex-1 px-4 py-6">
        {worksWithAuthor.length === 0 ? (
          <p className="text-center text-[var(--text-muted)] py-20">
            발행된 작품이 없습니다.
          </p>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {worksWithAuthor.map(({ work, authorName }) => (
              <WorkCard key={work.workId} work={work} authorName={authorName} />
            ))}
          </div>
        )}
      </main>

      <footer className="px-4 py-6 text-center text-xs text-[var(--text-muted)] border-t border-[var(--border)]">
        © 2026 teamMakeBooks
      </footer>
    </div>
  );
}
