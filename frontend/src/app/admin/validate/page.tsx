"use client"
import { useAdminWork } from "@/lib/admin";

import { useState, useEffect } from "react";
import Link from "next/link";

type Issue = { type: string; chapter?: number; msg: string };
type Warning = { type: string; msg: string };

export default function ValidatePage() {
  const { selectedWork } = useAdminWork();
  const [result, setResult] = useState<{
    total_chapters: number;
    issues: Issue[];
    warnings: Warning[];
    passed: boolean;
  } | null>(null);
  const [summaries, setSummaries] = useState<{ chapter_n: number; preview: string }[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<"validate" | "summaries">("validate");

  const runValidation = () => {
    setLoading(true);
    Promise.all([
      fetch(`/api/works/${selectedWork}/validate`).then((r) => r.json()),
      fetch(`/api/works/${selectedWork}/summaries`).then((r) => r.json()),
    ])
      .then(([v, s]) => {
        setResult(v);
        setSummaries(s.summaries || []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  };

  useEffect(() => { runValidation(); }, []);

  return (
    <div className="space-y-4">
      {/* 탭 */}
      <div className="flex gap-2">
        <button
          onClick={() => setActiveTab("validate")}
          className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
            activeTab === "validate" ? "bg-blue-500 text-white" : "bg-[var(--bg-chip)] text-[var(--text-secondary)]"
          }`}
        >
          검증 결과
        </button>
        <button
          onClick={() => setActiveTab("summaries")}
          className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
            activeTab === "summaries" ? "bg-blue-500 text-white" : "bg-[var(--bg-chip)] text-[var(--text-secondary)]"
          }`}
        >
          챕터 요약
        </button>
        <button
          onClick={runValidation}
          disabled={loading}
          className="ml-auto px-3 py-1.5 rounded-lg text-sm font-medium bg-[var(--bg-chip)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
        >
          {loading ? "검증 중..." : "다시 검증"}
        </button>
      </div>

      {/* 검증 탭 */}
      {activeTab === "validate" && result && (
        <div className="space-y-4">
          {/* 요약 카드 */}
          <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl p-4">
            <div className="flex items-center justify-between">
              <span className="text-sm font-semibold text-[var(--text-primary)]">
                전체 {result.total_chapters}화 검증
              </span>
              <span className={`text-xs font-medium px-2 py-1 rounded-full ${
                result.passed
                  ? "bg-emerald-500/20 text-emerald-400"
                  : "bg-red-500/20 text-red-400"
              }`}>
                {result.passed ? "통과" : "이슈 있음"}
              </span>
            </div>
          </div>

          {/* 에러 */}
          {result.issues.length > 0 && (
            <div className="space-y-2">
              <h3 className="text-sm font-semibold text-red-400">
                에러 ({result.issues.length})
              </h3>
              {result.issues.map((issue, i) => (
                <div key={i} className="bg-red-500/10 border border-red-500/20 rounded-lg p-3">
                  <div className="flex items-center gap-2 text-sm">
                    <span className="text-xs text-red-400 bg-red-500/20 px-1.5 py-0.5 rounded">
                      {issue.type}
                    </span>
                    {issue.chapter && (
                      <Link
                        href={`/admin/chapters/${issue.chapter}`}
                        className="text-blue-400 hover:underline"
                      >
                        {issue.chapter}화
                      </Link>
                    )}
                    <span className="text-[var(--text-secondary)]">{issue.msg}</span>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* 경고 */}
          {result.warnings.length > 0 && (
            <div className="space-y-2">
              <h3 className="text-sm font-semibold text-amber-400">
                경고 ({result.warnings.length})
              </h3>
              {result.warnings.map((w, i) => (
                <div key={i} className="bg-amber-500/10 border border-amber-500/20 rounded-lg p-3">
                  <div className="flex items-center gap-2 text-sm">
                    <span className="text-xs text-amber-400 bg-amber-500/20 px-1.5 py-0.5 rounded">
                      {w.type}
                    </span>
                    {"chapter" in w && (
                      <Link
                        href={`/admin/chapters/${w.chapter}`}
                        className="text-blue-400 hover:underline"
                      >
                        {String((w as Record<string, unknown>).chapter)}화
                      </Link>
                    )}
                    <span className="text-[var(--text-secondary)]">{w.msg}</span>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* 문제 없음 */}
          {result.issues.length === 0 && result.warnings.length === 0 && (
            <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-xl p-6 text-center">
              <p className="text-emerald-400 font-medium">검증 통과</p>
              <p className="text-xs text-[var(--text-muted)] mt-1">모든 챕터와 문서가 정상입니다.</p>
            </div>
          )}
        </div>
      )}

      {/* 요약 탭 */}
      {activeTab === "summaries" && (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold text-[var(--text-primary)]">
            챕터 요약 ({summaries.length}화)
          </h3>
          {summaries.length === 0 ? (
            <p className="text-sm text-[var(--text-muted)]">요약 파일이 없습니다.</p>
          ) : (
            <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl divide-y divide-[var(--border)] max-h-[60vh] overflow-auto">
              {summaries.map((s) => (
                <div key={s.chapter_n} className="flex items-start gap-3 px-4 py-3">
                  <span className="text-xs font-mono text-blue-400 bg-blue-500/10 px-1.5 py-0.5 rounded shrink-0 mt-0.5">
                    {s.chapter_n}
                  </span>
                  <Link
                    href={`/admin/chapters/${s.chapter_n}`}
                    className="text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)] line-clamp-2"
                  >
                    {s.preview}
                  </Link>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
