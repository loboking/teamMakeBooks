"use client";

import { useState, useEffect } from "react";

type ScheduleState = {
  is_running: boolean;
  start_chapter: number;
  end_chapter: number;
  daily_quota: number;
  current_chapter?: number;
};

type Props = {
  workId: string;
};

export default function ScheduleControl({ workId }: Props) {
  const [schedule, setSchedule] = useState<ScheduleState | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [editMode, setEditMode] = useState(false);

  const [startCh, setStartCh] = useState(1);
  const [endCh, setEndCh] = useState(100);
  const [dailyQuota, setDailyQuota] = useState(3);

  useEffect(() => {
    fetchSchedule();
  }, []);

  const fetchSchedule = async () => {
    try {
      const res = await fetch(`/api/works/${workId}/schedule`);
      if (res.ok) {
        const data = await res.json();
        setSchedule(data);
        setStartCh(data.start_chapter || 1);
        setEndCh(data.end_chapter || 100);
        setDailyQuota(data.daily_quota || 3);
      }
    } catch (e) {
      console.error("Failed to fetch schedule:", e);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await fetch(`/api/works/${workId}/schedule`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          start_chapter: startCh,
          end_chapter: endCh,
          daily_quota: dailyQuota,
        }),
      });
      if (res.ok) {
        setSchedule(await res.json());
        setEditMode(false);
      }
    } catch (e) {
      console.error("Failed to save schedule:", e);
    } finally {
      setSaving(false);
    }
  };

  const handleToggle = async () => {
    if (!schedule) return;
    try {
      const res = await fetch(`/api/works/${workId}/schedule/toggle`, {
        method: "POST",
      });
      if (res.ok) {
        setSchedule(await res.json());
      }
    } catch (e) {
      console.error("Failed to toggle schedule:", e);
    }
  };

  if (loading) {
    return (
      <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl p-6">
        <p className="text-center text-[var(--text-muted)]">로딩 중...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Status */}
      <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-[var(--text-primary)]">스케줄 상태</h3>
          <span className={`inline-flex items-center gap-2 px-3 py-1 rounded-full text-sm font-medium ${
            schedule?.is_running
              ? "bg-emerald-500/20 text-emerald-400"
              : "bg-zinc-500/20 text-zinc-400"
          }`}>
            <span className={`w-2 h-2 rounded-full ${schedule?.is_running ? "bg-emerald-400 animate-pulse" : "bg-zinc-400"}`} />
            {schedule?.is_running ? "진행중" : "일시정지"}
          </span>
        </div>

        <div className="flex gap-2">
          <button
            onClick={handleToggle}
            className={`flex-1 py-2.5 rounded-lg font-medium transition-colors ${
              schedule?.is_running
                ? "bg-amber-500/20 text-amber-400 hover:bg-amber-500/30"
                : "bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30"
            }`}
          >
            {schedule?.is_running ? "일시정지" : "시작"}
          </button>
          <button
            onClick={() => setEditMode(true)}
            className="px-4 py-2.5 rounded-lg bg-[var(--bg-chip)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
          >
            설정
          </button>
        </div>
      </div>

      {/* Edit mode */}
      {editMode && (
        <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl p-6">
          <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-4">스케줄 설정</h3>
          <div className="space-y-4">
            <div>
              <label className="block text-sm text-[var(--text-secondary)] mb-2">
                시작 챕터
              </label>
              <input
                type="number"
                value={startCh}
                onChange={(e) => setStartCh(Number(e.target.value))}
                className="w-full px-3 py-2 rounded-lg bg-[var(--bg-base)] border border-[var(--border)] text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-blue-500/50"
              />
            </div>
            <div>
              <label className="block text-sm text-[var(--text-secondary)] mb-2">
                종료 챕터
              </label>
              <input
                type="number"
                value={endCh}
                onChange={(e) => setEndCh(Number(e.target.value))}
                className="w-full px-3 py-2 rounded-lg bg-[var(--bg-base)] border border-[var(--border)] text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-blue-500/50"
              />
            </div>
            <div>
              <label className="block text-sm text-[var(--text-secondary)] mb-2">
                일일 생성량
              </label>
              <input
                type="number"
                value={dailyQuota}
                onChange={(e) => setDailyQuota(Number(e.target.value))}
                className="w-full px-3 py-2 rounded-lg bg-[var(--bg-base)] border border-[var(--border)] text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-blue-500/50"
              />
            </div>
            <div className="flex gap-2 pt-2">
              <button
                onClick={handleSave}
                disabled={saving}
                className="flex-1 py-2.5 rounded-lg bg-blue-500 text-white font-medium hover:bg-blue-600 disabled:opacity-50 transition-colors"
              >
                {saving ? "저장 중..." : "저장"}
              </button>
              <button
                onClick={() => setEditMode(false)}
                className="px-4 py-2.5 rounded-lg bg-[var(--bg-chip)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
              >
                취소
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Current progress */}
      {schedule && schedule.current_chapter && (
        <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl p-6">
          <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-2">현재 진행</h3>
          <p className="text-2xl font-bold text-blue-400">
            {schedule.current_chapter}화
          </p>
          <div className="mt-3 h-2 bg-[var(--bg-chip)] rounded-full overflow-hidden">
            <div
              className="h-full bg-blue-500 transition-all duration-300"
              style={{
                width: `${((schedule.current_chapter - startCh) / (endCh - startCh)) * 100}%`,
              }}
            />
          </div>
        </div>
      )}
    </div>
  );
}
