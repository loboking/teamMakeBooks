import { getWork } from "@/lib/data";
import ChapterDetailClient from "./ChapterDetailClient";

const WORK_ID = "modern_fantasy_game_01";

export function generateStaticParams() {
  // Pre-generate for chapters 1-100
  return Array.from({ length: 100 }, (_, i) => ({ n: String(i + 1) }));
}

export default async function ChapterDetailPage({
  params,
}: {
  params: Promise<{ n: string }>;
}) {
  const { n } = await params;
  const chapterN = Number(n);
  const work = getWork(WORK_ID);

  return (
    <ChapterDetailClient chapterN={chapterN} workTitle={work?.title || "무등급헌터"} />
  );
}
