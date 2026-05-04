"use client";

import { useState, useEffect } from "react";

type Config = {
  temperature: number;
  num_predict: number;
  [key: string]: any;
};

const WORK_ID = "modern_fantasy_game_01";

export default function SettingsPage() {
  const [config, setConfig] = useState<Config | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState(false);

  const [temperature, setTemperature] = useState(0.7);
  const [numPredict, setNumPredict] = useState(4096);

  useEffect(() => {
    fetchConfig();
  }, []);

  const fetchConfig = async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/works/${WORK_ID}/config`);
      if (res.ok) {
        const data = await res.json();
        setConfig(data);
        setTemperature(data.temperature ?? 0.7);
        setNumPredict(data.num_predict ?? 4096);
      }
    } catch (e) {
      console.error("Failed to fetch config:", e);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await fetch(`/api/works/${WORK_ID}/config`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ temperature, num_predict: numPredict }),
      });
      if (res.ok) {
        await fetchConfig();
        setEditing(false);
      }
    } catch (e) {
      console.error("Failed to save config:", e);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h1 className="text-xl font-bold text-[var(--text-primary)] mb-1">설정</h1>
        <p className="text-sm text-[var(--text-muted)]">모델 생성 파라미터를 설정합니다.</p>
      </div>

      {/* Generation settings */}
      <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-[var(--text-primary)]">생성 파라미터</h3>
          {!editing && (
            <button
              onClick={() => setEditing(true)}
              className="text-sm text-blue-400 hover:text-blue-300 transition-colors"
            >
              수정
            </button>
          )}
        </div>

        <div className="space-y-4">
          <div>
            <label className="block text-sm text-[var(--text-secondary)] mb-2">
              Temperature (0 ~ 2)
            </label>
            <input
              type="number"
              step="0.1"
              min="0"
              max="2"
              value={temperature}
              onChange={(e) => setTemperature(Number(e.target.value))}
              disabled={!editing}
              className={`w-full px-3 py-2 rounded-lg bg-[var(--bg-base)] border border-[var(--border)] text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-blue-500/50 ${
                !editing ? "cursor-not-allowed opacity-70" : ""
              }`}
            />
            <p className="mt-1 text-xs text-[var(--text-muted)]">
              낮을수록 더 결정적인 출력, 높을수록 더 창의적인 출력
            </p>
          </div>

          <div>
            <label className="block text-sm text-[var(--text-secondary)] mb-2">
              Num Predict (최대 토큰 수)
            </label>
            <input
              type="number"
              min="128"
              max="32768"
              step="128"
              value={numPredict}
              onChange={(e) => setNumPredict(Number(e.target.value))}
              disabled={!editing}
              className={`w-full px-3 py-2 rounded-lg bg-[var(--bg-base)] border border-[var(--border)] text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-blue-500/50 ${
                !editing ? "cursor-not-allowed opacity-70" : ""
              }`}
            />
            <p className="mt-1 text-xs text-[var(--text-muted)]">
              생성할 최대 토큰 수 (클수록 긴 본문 생성 가능)
            </p>
          </div>
        </div>

        {editing && (
          <div className="flex gap-2 mt-4 pt-4 border-t border-[var(--border)]">
            <button
              onClick={handleSave}
              disabled={saving}
              className="flex-1 py-2.5 rounded-lg bg-blue-500 text-white font-medium hover:bg-blue-600 disabled:opacity-50 transition-colors"
            >
              {saving ? "저장 중..." : "저장"}
            </button>
            <button
              onClick={() => {
                setEditing(false);
                setTemperature(config?.temperature ?? 0.7);
                setNumPredict(config?.num_predict ?? 4096);
              }}
              className="px-4 py-2.5 rounded-lg bg-[var(--bg-chip)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
            >
              취소
            </button>
          </div>
        )}
      </div>

      {/* Config preview */}
      {config && (
        <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl p-6">
          <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-4">Config.yaml (읽기 전용)</h3>
          <pre className="bg-[var(--bg-chip)] rounded-lg p-4 text-xs text-[var(--text-secondary)] overflow-x-auto">
            {JSON.stringify(config, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
