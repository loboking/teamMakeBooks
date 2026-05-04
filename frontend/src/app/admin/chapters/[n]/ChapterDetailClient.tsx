"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import ChapterEditor from "@/components/admin/ChapterEditor";
import ReviewReport from "@/components/admin/ReviewReport";
import StatusBadge from "@/components/admin/StatusBadge";
import { useAdminWork } from "@/lib/admin";

type Chapter = {
  n: number;
  title: string;
  body: string;
  status: string;
  published: boolean;
  reviewers?: Array<{
    name: string;
    score: number;
    comment?: string;
  }>;
};

type Props = {
  chapterN: number;
  workTitle: string;
};

export default function ChapterDetailClient({ chapterN, workTitle }: Props) {
  const { selectedWork } = useAdminWork();
  const [chapter, setChapter] = useState<Chapter | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchChapter();
  }, [chapterN]);

  const fetchChapter = async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/works/${selectedWork}/chapters/${chapterN}`);
      if (res.ok) {
        const data = await res.json();
        setChapter(data);
      }
    } catch (e) {
      console.error("Failed to fetch chapter:", e);
    } finally {
      setLoading(false);
    }
  };

  const handleSaveBody = async (content: string) => {
    setSaving(true);
    try {
      const res = await fetch(`/api/works/${selectedWork}/chapters/${chapterN}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ body: content }),
      });
      if (res.ok) {
        setChapter((prev) => (prev ? { ...prev, body: content } : null));
      }
    } catch (e) {
      console.error("Failed to save chapter:", e);
    } finally {
      setSaving(false);
    }
  };

  const handleRegenerate = async () => {
    if (!confirm("이 챕터를 다시 생성하시겠습니까?")) return;
    try {
      const res = await fetch(`/api/works/${selectedWork}/chapters/${chapterN}/regenerate`, {
        method: "POST",
      });
      if (res.ok) {
        await fetchChapter();
      }
    } catch (e) {
      console.error("Failed to regenerate:", e);
    }
  };

  const handleReReview = async () => {
    try {
      const res = await fetch(`/api/works/${selectedWork}/chapters/${chapterN}/review`, {
        method: "POST",
      });
      if (res.ok) {
        await fetchChapter();
      }
    } catch (e) {
      console.error("Failed to request review:", e);
    }
  };

  const handlePublish = async () => {
    if (!confirm("텔레그램에 발행하시겠습니까?")) return;
    try {
      const res = await fetch(`/api/works/${selectedWork}/chapters/${chapterN}/publish`, {
        method: "POST",
      });
      if (res.ok) {
        await fetchChapter();
      }
    } catch (e) {
      console.error("Failed to publish:", e);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!chapter) {
    return (
      <div className="text-center py-20">
        <p className="text-[var(--text-muted)]">챕터를 찾을 수 없습니다.</p>
        <Link href="/admin/chapters" className="inline-block mt-4 px-4 py-2 rounded-lg bg-[var(--bg-chip)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]">
          목록으로
        </Link>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <Link href="/admin/chapters" className="text-sm text-[var(--text-muted)] hover:text-[var(--text-primary)] mb-2 inline-block">
            ← 챕터 목록
          </Link>
          <h1 className="text-2xl font-bold text-[var(--text-primary)]">
            {chapter.title || `${chapter.n}화`}
          </h1>
          <div className="flex items-center gap-3 mt-2">
            <StatusBadge status={chapter.status === "passed" ? "합격" : chapter.status === "failed" ? "실패" : "대기"} />
            {chapter.published ? (
              <StatusBadge status="발행" />
            ) : (
              <StatusBadge status="미발행" />
            )}
          </div>
        </div>
      </div>

      {/* Actions */}
      <div className="flex flex-wrap gap-2">
        <button
          onClick={handleRegenerate}
          className="px-4 py-2 rounded-lg bg-[var(--bg-chip)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
        >
          재생성
        </button>
        <button
          onClick={handleReReview}
          className="px-4 py-2 rounded-lg bg-[var(--bg-chip)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
        >
          재검수
        </button>
        <button
          onClick={handlePublish}
          disabled={chapter.published}
          className={`px-4 py-2 rounded-lg font-medium transition-colors ${
            chapter.published
              ? "bg-[var(--bg-chip)] text-[var(--text-muted)] cursor-not-allowed"
              : "bg-purple-500/20 text-purple-400 hover:bg-purple-500/30"
          }`}
        >
          텔레그램 발행
        </button>
      </div>

      {/* Editor */}
      <ChapterEditor content={chapter.body} onSave={handleSaveBody} />

      {/* Review report */}
      <ReviewReport status={chapter.status} reviewers={chapter.reviewers || []} />
    </div>
  );
}
