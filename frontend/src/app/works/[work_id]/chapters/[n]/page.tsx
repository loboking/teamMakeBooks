import { notFound } from "next/navigation";
import { getChapter, getWork, listChapters, listWorks } from "@/lib/data";
import ReaderClient from "@/components/ReaderClient";

export function generateStaticParams() {
  const params: { work_id: string; n: string }[] = [];
  for (const w of listWorks()) {
    for (const c of listChapters(w.workId)) {
      params.push({ work_id: w.workId, n: String(c.n) });
    }
  }
  return params;
}

export default async function ChapterPage({
  params,
}: {
  params: Promise<{ work_id: string; n: string }>;
}) {
  const { work_id, n } = await params;
  const chapterN = parseInt(n, 10);
  if (isNaN(chapterN)) notFound();

  const chapter = getChapter(work_id, chapterN);
  if (!chapter) notFound();

  const work = getWork(work_id);
  const totalChapters = work?.publishedChapters ?? chapterN;

  return (
    <ReaderClient
      workId={work_id}
      chapterN={chapterN}
      totalChapters={totalChapters}
      chapterTitle={`${chapterN}화. ${chapter.meta.title}`}
      body={chapter.body}
    />
  );
}
