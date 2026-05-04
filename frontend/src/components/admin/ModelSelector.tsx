"use client";

import { useState, useEffect } from "react";

type ModelConfig = {
  writer: string;
  reviewer: string;
  publisher: string;
};

type ModelsResponse = {
  available: string[];
  current: ModelConfig;
};

type Props = {
  workId: string;
};

export default function ModelSelector({ workId }: Props) {
  const [models, setModels] = useState<ModelsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);

  useEffect(() => {
    fetchModels();
  }, []);

  const fetchModels = async () => {
    try {
      const res = await fetch(`/api/works/${workId}/models`);
      if (res.ok) {
        const data = await res.json();
        setModels(data);
      }
    } catch (e) {
      console.error("Failed to fetch models:", e);
    } finally {
      setLoading(false);
    }
  };

  const handleModelChange = async (role: keyof ModelConfig, model: string) => {
    if (!models) return;
    try {
      const res = await fetch(`/api/works/${workId}/models`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ [role]: model }),
      });
      if (res.ok) {
        setModels({ ...models, [role]: model });
      }
    } catch (e) {
      console.error("Failed to update model:", e);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const res = await fetch(`/api/works/${workId}/test-generate`, {
        method: "POST",
      });
      if (res.ok) {
        const data = await res.json();
        setTestResult(data.preview || "테스트 생성 완료");
      }
    } catch (e) {
      setTestResult("테스트 실패");
    } finally {
      setTesting(false);
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
      {/* Current models */}
      <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl p-6">
        <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-4">현재 모델</h3>
        <div className="space-y-4">
          {models && (
            <>
              <ModelRow
                label="작가 모델"
                value={models.current.writer}
                options={models.available}
                onChange={(model) => handleModelChange("writer", model)}
              />
              <ModelRow
                label="검수 모델"
                value={models.current.reviewer}
                options={models.available}
                onChange={(model) => handleModelChange("reviewer", model)}
              />
              <ModelRow
                label="발행 모델"
                value={models.current.publisher}
                options={models.available}
                onChange={(model) => handleModelChange("publisher", model)}
              />
            </>
          )}
        </div>
      </div>

      {/* Test */}
      <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl p-6">
        <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-4">테스트 생성</h3>
        <button
          onClick={handleTest}
          disabled={testing}
          className="w-full py-2.5 rounded-lg bg-blue-500 text-white font-medium hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {testing ? "생성 중..." : "1화 테스트 생성"}
        </button>
        {testResult && (
          <div className="mt-4 p-4 bg-[var(--bg-chip)] rounded-lg">
            <p className="text-sm text-[var(--text-secondary)] whitespace-pre-wrap">
              {testResult}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

type ModelRowProps = {
  label: string;
  value: string;
  options: string[];
  onChange: (model: string) => void;
};

function ModelRow({ label, value, options, onChange }: ModelRowProps) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-sm text-[var(--text-secondary)]">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="px-3 py-2 rounded-lg bg-[var(--bg-base)] border border-[var(--border)] text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-blue-500/50"
      >
        {options.map((opt) => (
          <option key={opt} value={opt}>
            {opt}
          </option>
        ))}
      </select>
    </div>
  );
}
