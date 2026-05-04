"use client";

import { useState } from "react";

type Props = {
  content: string;
  onSave?: (content: string) => void;
  readOnly?: boolean;
};

export default function ChapterEditor({ content, onSave, readOnly = false }: Props) {
  const [value, setValue] = useState(content);
  const [isDirty, setIsDirty] = useState(false);

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setValue(e.target.value);
    setIsDirty(true);
  };

  const handleSave = () => {
    onSave?.(value);
    setIsDirty(false);
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">본문</h3>
        {!readOnly && (
          <div className="flex gap-2">
            {isDirty && (
              <button
                onClick={() => {
                  setValue(content);
                  setIsDirty(false);
                }}
                className="px-3 py-1.5 rounded-lg text-sm font-medium bg-[var(--bg-chip)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
              >
                취소
              </button>
            )}
            <button
              onClick={handleSave}
              disabled={!isDirty}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                isDirty
                  ? "bg-blue-500 text-white hover:bg-blue-600"
                  : "bg-[var(--bg-chip)] text-[var(--text-muted)] cursor-not-allowed"
              }`}
            >
              저장
            </button>
          </div>
        )}
      </div>
      <textarea
        value={value}
        onChange={handleChange}
        readOnly={readOnly}
        className={`w-full h-[500px] p-4 rounded-lg bg-[var(--bg-card)] border border-[var(--border)] text-[var(--text-primary)] text-sm leading-relaxed resize-none focus:outline-none focus:ring-2 focus:ring-blue-500/50 ${
          readOnly ? "cursor-default" : ""
        }`}
        placeholder="챕터 내용이 없습니다."
      />
      {isDirty && (
        <p className="text-xs text-amber-400">* 변경사항이 저장되지 않았습니다.</p>
      )}
    </div>
  );
}
