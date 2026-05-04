"use client";

import { useState } from "react";

type Chapter = {
  n: number;
  title: string;
  status: string;
  published: boolean;
  created_at: string;
};

type Props = {
  chapters: Chapter[];
  onRefresh?: () => void;
};

const filterOptions = [
  { value: "all", label: "전체" },
  { value: "passed", label: "검수합격" },
  { value: "failed", label: "검수실패" },
  { value: "pending", label: "미검수" },
];

export default function ChapterTable({ chapters, onRefresh }: Props) {
  const [filter, setFilter] = useState("all");

  const filteredChapters = chapters.filter((ch) => {
    if (filter === "all") return true;
    if (filter === "passed") return ch.status === "passed";
    if (filter === "failed") return ch.status === "failed";
    if (filter === "pending") return ch.status === "pending" || !ch.status;
    return true;
  });

  const getStatusLabel = (status: string) => {
    if (status === "passed") return "합격";
    if (status === "failed") return "실패";
    return "대기";
  };

  return (
    <div className="space-y-4">
      {/* Filter */}
      <div className="flex items-center justify-between">
        <div className="flex gap-2">
          {filterOptions.map((opt) => (
            <button
              key={opt.value}
              onClick={() => setFilter(opt.value)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                filter === opt.value
                  ? "bg-blue-500 text-white"
                  : "bg-[var(--bg-chip)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
        {onRefresh && (
          <button
            onClick={onRefresh}
            className="p-2 rounded-lg bg-[var(--bg-chip)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
              <path d="M3 3v5h5" />
              <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16" />
              <path d="M16 21h5v-5" />
            </svg>
          </button>
        )}
      </div>

      {/* Table */}
      <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-[var(--bg-chip)] border-b border-[var(--border)]">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-semibold text-[var(--text-secondary)] uppercase">
                  번호
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-[var(--text-secondary)] uppercase">
                  제목
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-[var(--text-secondary)] uppercase">
                  검수
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-[var(--text-secondary)] uppercase">
                  발행
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-[var(--text-secondary)] uppercase">
                  생성일
                </th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-[var(--text-secondary)] uppercase">
                  액션
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--border)]">
              {filteredChapters.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-12 text-center text-[var(--text-muted)]">
                    표시할 챕터가 없습니다.
                  </td>
                </tr>
              ) : (
                filteredChapters.map((ch) => (
                  <tr
                    key={ch.n}
                    className="hover:bg-[var(--bg-chip)] transition-colors cursor-pointer"
                  >
                    <td className="px-4 py-3 text-sm font-mono text-[var(--text-primary)]">
                      {ch.n}
                    </td>
                    <td className="px-4 py-3">
                      <div className="text-sm font-medium text-[var(--text-primary)]">
                        {ch.title || `${ch.n}화`}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center gap-1.5 text-xs font-medium ${
                        ch.status === "passed"
                          ? "text-emerald-400"
                          : ch.status === "failed"
                          ? "text-red-400"
                          : "text-amber-400"
                      }`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${
                          ch.status === "passed"
                            ? "bg-emerald-400"
                            : ch.status === "failed"
                            ? "bg-red-400"
                            : "bg-amber-400"
                        }`} />
                        {getStatusLabel(ch.status)}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {ch.published ? (
                        <span className="inline-flex items-center gap-1 text-xs text-purple-400">
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M20 6L9 17l-5-5" />
                          </svg>
                          발행
                        </span>
                      ) : (
                        <span className="text-xs text-[var(--text-muted)]">미발행</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-xs text-[var(--text-muted)]">
                      {ch.created_at
                        ? new Date(ch.created_at).toLocaleDateString("ko-KR")
                        : "-"}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-1">
                        <a
                          href={`/admin/chapters/${ch.n}`}
                          className="p-1.5 rounded hover:bg-[var(--bg-base)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
                          title="상세보기"
                        >
                          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />
                            <path d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7Z" />
                          </svg>
                        </a>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
