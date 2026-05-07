"use client";

import { useEffect, useState } from "react";

type Schedule = {
  enabled: boolean;
  frequency: "daily" | "hourly" | "weekly" | "manual";
  hour: number;
  minute: number;
  batch_size: number;
  paused: boolean;
  last_run_at: string;
  last_published_n: number;
  last_status: string;
  last_error: string;
};

type ScheduleResponse = {
  work_id: string;
  schedule: Schedule;
  next_run_at: string | null;
  next_chapter_n: number;
};

type Props = { workId: string };

const FREQUENCIES = [
  { value: "daily", label: "매일" },
  { value: "hourly", label: "매시간" },
  { value: "weekly", label: "매주(월)" },
  { value: "manual", label: "수동" },
] as const;

const BATCH_SIZES = [1, 3, 5, 10];

export default function ScheduleControl({ workId }: Props) {
  const [data, setData] = useState<ScheduleResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [enabled, setEnabled] = useState(false);
  const [frequency, setFrequency] = useState<Schedule["frequency"]>("daily");
  const [hour, setHour] = useState(9);
  const [minute, setMinute] = useState(0);
  const [batchSize, setBatchSize] = useState(1);

  const fetchSchedule = async () => {
    try {
      const res = await fetch(`/api/works/${workId}/schedule`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const d: ScheduleResponse = await res.json();
      setData(d);
      setEnabled(d.schedule.enabled);
      setFrequency(d.schedule.frequency);
      setHour(d.schedule.hour);
      setMinute(d.schedule.minute);
      setBatchSize(d.schedule.batch_size);
      setError(null);
    } catch (e: any) {
      setError(`스케줄 로드 실패: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (workId) fetchSchedule();
  }, [workId]);

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        enabled: String(enabled),
        frequency,
        hour: String(hour),
        minute: String(minute),
        batch_size: String(batchSize),
      });
      const res = await fetch(`/api/works/${workId}/schedule?${params}`, { method: "PUT" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await fetchSchedule();
    } catch (e: any) {
      setError(`저장 실패: ${e.message}`);
    } finally {
      setSaving(false);
    }
  };

  const togglePause = async () => {
    if (!data) return;
    const action = data.schedule.paused ? "resume" : "pause";
    try {
      await fetch(`/api/works/${workId}/schedule/${action}`, { method: "POST" });
      await fetchSchedule();
    } catch (e: any) {
      setError(`일시정지 토글 실패: ${e.message}`);
    }
  };

  const runNow = async () => {
    setRunning(true);
    setError(null);
    try {
      const params = new URLSearchParams({ batch_size: String(batchSize) });
      const res = await fetch(`/api/works/${workId}/schedule/run-now?${params}`, { method: "POST" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const j = await res.json();
      alert(`즉시 실행 시작: ch${j.from_chapter}~ch${j.to_chapter}\ntask_id=${j.task_id}`);
      await fetchSchedule();
    } catch (e: any) {
      setError(`즉시 실행 실패: ${e.message}`);
    } finally {
      setRunning(false);
    }
  };

  if (loading) return <div className="text-sm text-[var(--text-muted)]">로딩...</div>;
  if (!data) return <div className="text-sm text-red-500">{error || "스케줄 데이터 없음"}</div>;

  const sch = data.schedule;
  const nextRun = data.next_run_at ? new Date(data.next_run_at).toLocaleString("ko-KR") : null;

  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--card-bg)] p-5 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-[var(--text-primary)]">자동 발행 스케줄</h2>
        <span
          className={`text-xs px-2 py-1 rounded ${
            sch.enabled && !sch.paused
              ? "bg-green-100 text-green-700"
              : sch.paused
              ? "bg-yellow-100 text-yellow-700"
              : "bg-gray-100 text-gray-600"
          }`}
        >
          {sch.enabled && !sch.paused ? "활성" : sch.paused ? "일시정지" : "비활성"}
        </span>
      </div>

      {error && (
        <div className="text-sm text-red-600 bg-red-50 px-3 py-2 rounded">{error}</div>
      )}

      <div className="grid grid-cols-2 gap-3 text-sm">
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
          />
          <span>활성화</span>
        </label>

        <label className="flex items-center gap-2">
          <span className="w-16 text-[var(--text-muted)]">빈도</span>
          <select
            value={frequency}
            onChange={(e) => setFrequency(e.target.value as Schedule["frequency"])}
            className="flex-1 border border-[var(--border)] rounded px-2 py-1 bg-[var(--input-bg)]"
          >
            {FREQUENCIES.map((f) => (
              <option key={f.value} value={f.value}>{f.label}</option>
            ))}
          </select>
        </label>

        <label className="flex items-center gap-2">
          <span className="w-16 text-[var(--text-muted)]">시작 시각</span>
          <input
            type="number" min={0} max={23} value={hour}
            onChange={(e) => setHour(Number(e.target.value))}
            className="w-16 border border-[var(--border)] rounded px-2 py-1 bg-[var(--input-bg)]"
          />
          <span>시</span>
          <input
            type="number" min={0} max={59} value={minute}
            onChange={(e) => setMinute(Number(e.target.value))}
            className="w-16 border border-[var(--border)] rounded px-2 py-1 bg-[var(--input-bg)]"
          />
          <span>분 (KST)</span>
        </label>

        <label className="flex items-center gap-2">
          <span className="w-16 text-[var(--text-muted)]">회차당 수</span>
          <select
            value={batchSize}
            onChange={(e) => setBatchSize(Number(e.target.value))}
            className="flex-1 border border-[var(--border)] rounded px-2 py-1 bg-[var(--input-bg)]"
          >
            {BATCH_SIZES.map((n) => (
              <option key={n} value={n}>{n}화</option>
            ))}
          </select>
        </label>
      </div>

      <div className="text-xs text-[var(--text-muted)] space-y-1">
        <div>다음 실행: {nextRun || "—"}</div>
        <div>다음 발행 화: ch{String(data.next_chapter_n).padStart(3, "0")}</div>
        <div>마지막 실행: {sch.last_run_at || "—"} ({sch.last_status})</div>
        {sch.last_error && (
          <div className="text-red-500">에러: {sch.last_error}</div>
        )}
      </div>

      <div className="flex gap-2">
        <button
          onClick={save}
          disabled={saving}
          className="px-4 py-2 bg-[var(--primary)] text-white rounded text-sm hover:opacity-90 disabled:opacity-50"
        >
          {saving ? "저장 중..." : "저장"}
        </button>
        <button
          onClick={togglePause}
          disabled={!sch.enabled}
          className="px-4 py-2 border border-[var(--border)] rounded text-sm hover:bg-[var(--card-bg-hover)] disabled:opacity-50"
        >
          {sch.paused ? "재개" : "일시정지"}
        </button>
        <button
          onClick={runNow}
          disabled={running}
          className="px-4 py-2 border border-[var(--border)] rounded text-sm hover:bg-[var(--card-bg-hover)] disabled:opacity-50"
        >
          {running ? "실행 중..." : `즉시 실행 (${batchSize}화)`}
        </button>
      </div>
    </div>
  );
}
