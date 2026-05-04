"use client";

import { useState, useEffect } from "react";
import { useAdminWork } from "@/lib/admin";
import StatusBadge from "@/components/admin/StatusBadge";
import PipelineStatus from "@/components/admin/PipelineStatus";
import Link from "next/link";

export default function AdminPage() {
  const { selectedWork } = useAdminWork();
  const [stats, setStats] = useState<any>(null);
  const [chapterStats, setChapterStats] = useState({ total: 0, passed: 0, failed: 0, pending: 0 });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      fetch(`/api/works/${selectedWork}`).then((r) => r.ok ? r.json() : null).catch(() => null),
      fetch(`/api/works/${selectedWork}/chapters`).then((r) => r.ok ? r.json() : []).catch(() => []),
    ]).then(([s, chapters]) => {
      setStats(s);
      setChapterStats({
        total: chapters.length,
        passed: chapters.filter((ch: any) => ch.status === "passed").length,
        failed: chapters.filter((ch: any) => ch.status === "failed").length,
        pending: chapters.filter((ch: any) => !ch.status || ch.status === "pending").length,
      });
      setLoading(false);
    });
  }, [selectedWork]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {stats && (
        <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl p-6">
          <h2 className="text-lg font-bold text-[var(--text-primary)] mb-4">{stats.title || selectedWork}</h2>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            <div>
              <p className="text-xs text-[var(--text-muted)]">장르</p>
              <p className="text-sm font-medium text-[var(--text-primary)]">
                {stats.genre || "-"}
              </p>
            </div>
            <div>
              <p className="text-xs text-[var(--text-muted)]">총 챕터</p>
              <p className="text-sm font-medium text-[var(--text-primary)]">{chapterStats.total}화</p>
            </div>
            <div>
              <p className="text-xs text-[var(--text-muted)]">발행 챕터</p>
              <p className="text-sm font-medium text-[var(--text-primary)]">{stats.published_chapters ?? "-"}화</p>
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Link href="/admin/chapters?filter=passed" className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl p-6 hover:border-emerald-500/30 transition-colors">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs text-[var(--text-muted)]">검수 합격</p>
              <p className="text-2xl font-bold text-emerald-400">{chapterStats.passed}</p>
            </div>
            <div className="w-10 h-10 rounded-full bg-emerald-500/20 flex items-center justify-center">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-emerald-400">
                <path d="M20 6L9 17l-5-5" />
              </svg>
            </div>
          </div>
        </Link>

        <Link href="/admin/chapters?filter=failed" className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl p-6 hover:border-red-500/30 transition-colors">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs text-[var(--text-muted)]">검수 실패</p>
              <p className="text-2xl font-bold text-red-400">{chapterStats.failed}</p>
            </div>
            <div className="w-10 h-10 rounded-full bg-red-500/20 flex items-center justify-center">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-red-400">
                <path d="M18 6L6 18M6 6l12 12" />
              </svg>
            </div>
          </div>
        </Link>

        <Link href="/admin/chapters?filter=pending" className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl p-6 hover:border-amber-500/30 transition-colors">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs text-[var(--text-muted)]">검수 대기</p>
              <p className="text-2xl font-bold text-amber-400">{chapterStats.pending}</p>
            </div>
            <div className="w-10 h-10 rounded-full bg-amber-500/20 flex items-center justify-center">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-amber-400">
                <circle cx="12" cy="12" r="10" />
                <path d="M12 6v6l4 2" />
              </svg>
            </div>
          </div>
        </Link>
      </div>

      <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-[var(--text-primary)]">현재 스케줄</h3>
          {stats?.schedule?.is_running ? (
            <StatusBadge status="진행중" />
          ) : (
            <StatusBadge status="대기" />
          )}
        </div>
        {stats?.schedule && (
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-[var(--text-secondary)]">범위</span>
              <span className="text-[var(--text-primary)]">
                {stats.schedule.start_chapter} ~ {stats.schedule.end_chapter}화
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-[var(--text-secondary)]">일일 할당량</span>
              <span className="text-[var(--text-primary)]">
                {stats.schedule.daily_quota}화/일
              </span>
            </div>
            {stats.schedule.current_chapter && (
              <div className="flex justify-between">
                <span className="text-[var(--text-secondary)]">현재 챕터</span>
                <span className="text-[var(--text-primary)] font-medium">
                  {stats.schedule.current_chapter}화
                </span>
              </div>
            )}
          </div>
        )}
      </div>

      <PipelineStatus workId={selectedWork} />
    </div>
  );
}
