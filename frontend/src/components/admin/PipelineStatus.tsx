"use client";

import { useState, useEffect } from "react";

type PipelineJob = {
  id: string;
  chapter_n: number;
  status: "running" | "completed" | "failed";
  stage: string;
  started_at: string;
  completed_at?: string;
};

type Props = {
  workId: string;
};

export default function PipelineStatus({ workId }: Props) {
  const [jobs, setJobs] = useState<PipelineJob[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchJobs();
    const interval = setInterval(fetchJobs, 5000);
    return () => clearInterval(interval);
  }, []);

  const fetchJobs = async () => {
    try {
      const res = await fetch(`/api/works/${workId}/pipelines`);
      if (res.ok) {
        const data = await res.json();
        setJobs(data.jobs || []);
      }
    } catch (e) {
      console.error("Failed to fetch jobs:", e);
    } finally {
      setLoading(false);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "running":
        return <span className="inline-flex items-center gap-1.5 text-xs font-medium text-blue-400">
          <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
          진행중
        </span>;
      case "completed":
        return <span className="inline-flex items-center gap-1.5 text-xs font-medium text-emerald-400">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
          완료
        </span>;
      case "failed":
        return <span className="inline-flex items-center gap-1.5 text-xs font-medium text-red-400">
          <span className="w-1.5 h-1.5 rounded-full bg-red-400" />
          실패
        </span>;
      default:
        return null;
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">파이프라인 실행 이력</h3>
        <span className="text-xs text-[var(--text-muted)]">
          {jobs.filter((j) => j.status === "running").length}개 진행중
        </span>
      </div>

      <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-[var(--text-muted)]">로딩 중...</div>
        ) : jobs.length === 0 ? (
          <div className="p-8 text-center text-[var(--text-muted)]">실행 이력이 없습니다.</div>
        ) : (
          <div className="divide-y divide-[var(--border)]">
            {jobs.slice(0, 10).map((job) => (
              <div key={job.id} className="p-4 hover:bg-[var(--bg-chip)] transition-colors">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <span className="text-sm font-medium text-[var(--text-primary)]">
                      {job.chapter_n}화
                    </span>
                    {getStatusBadge(job.status)}
                  </div>
                  <span className="text-xs text-[var(--text-muted)]">
                    {job.stage}
                  </span>
                </div>
                <div className="mt-2 text-xs text-[var(--text-muted)]">
                  시작: {new Date(job.started_at).toLocaleString("ko-KR")}
                  {job.completed_at && (
                    <> · 완료: {new Date(job.completed_at).toLocaleString("ko-KR")}</>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
