import Link from "next/link";
import type { WorkSummary } from "@/lib/data";
import AiBadge from "./AiBadge";
import AiPersonaLabel from "./AiPersonaLabel";

const GENRE_COLORS: Record<string, string> = {
  modern_fantasy_game: "bg-indigo-900/40 text-indigo-300",
  romance: "bg-rose-900/40 text-rose-300",
  thriller: "bg-slate-700/40 text-slate-300",
};

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
  const idx = workId.length % COVER_GRADIENTS.length;
  return COVER_GRADIENTS[idx];
}

type Props = { work: WorkSummary; authorName: string };

export default function WorkCard({ work, authorName }: Props) {
  const genreColor = GENRE_COLORS[work.genre] ?? "bg-zinc-800 text-zinc-300";
  const genreLabel = GENRE_LABELS[work.genre] ?? work.genre;

  return (
    <Link
      href={`/works/${work.workId}`}
      className="block rounded-xl overflow-hidden border border-[var(--border)] bg-[var(--bg-card)] hover:border-violet-500/60 transition-colors duration-200 active:scale-[0.98]"
    >
      {/* Cover */}
      <div
        className={`relative h-44 bg-gradient-to-br ${coverGradient(work.workId)} flex items-end p-4`}
      >
        <h2 className="text-white font-bold text-xl leading-snug drop-shadow-lg">
          {work.title}
        </h2>
      </div>

      {/* Body */}
      <div className="p-4 space-y-3">
        {/* Badges row */}
        <div className="flex flex-wrap gap-2 items-center">
          <span
            className={`text-xs px-2 py-0.5 rounded-md font-medium ${genreColor}`}
          >
            {genreLabel}
          </span>
          {work.isAiPersona && <AiBadge size="sm" />}
        </div>

        {/* Author */}
        <div className="flex items-center gap-2">
          <span className="text-sm text-[var(--text-secondary)]">
            {authorName}
          </span>
          {work.isAiPersona && <AiPersonaLabel />}
        </div>

        {/* Chapter count */}
        <p className="text-xs text-[var(--text-muted)]">
          총 {work.publishedChapters}화 발행
        </p>
      </div>
    </Link>
  );
}
