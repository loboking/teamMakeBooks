"use client"
import { useAdminWork } from "@/lib/admin";

import { useState, useEffect } from "react";

const DOCS = [
  { key: "world_bible", label: "세계관", icon: "🌍" },
  { key: "characters", label: "등장인물", icon: "👥" },
  { key: "plot_outline", label: "플롯 개요", icon: "📋" },
  { key: "naming_table", label: "호칭표", icon: "🏷️" },
  { key: "theme", label: "테마/약속", icon: "🎯" },
];

export default function PrepPage() {
  const { selectedWork } = useAdminWork();
  const [activeDoc, setActiveDoc] = useState("world_bible");
  const [content, setContent] = useState("");
  const [saved, setSaved] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setSaved(true);
    setContent("로딩...");
    fetch(`/api/works/${selectedWork}/prep/${activeDoc}`)
      .then((r) => r.json())
      .then((d) => setContent(d.content || ""))
      .catch(() => setContent(""));
  }, [activeDoc, selectedWork]);

  const handleSave = () => {
    setSaving(true);
    fetch(`/api/works/${selectedWork}/prep/${activeDoc}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
    })
      .then(() => { setSaved(true); setSaving(false); })
      .catch(() => setSaving(false));
  };

  const doc = DOCS.find((d) => d.key === activeDoc);

  return (
    <div className="flex flex-col h-[calc(100vh-3rem)] md:h-[calc(100vh-3.5rem)]">
      {/* 문서 탭 */}
      <div className="flex gap-1 overflow-x-auto pb-2 shrink-0">
        {DOCS.map((d) => (
          <button
            key={d.key}
            onClick={() => setActiveDoc(d.key)}
            className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium whitespace-nowrap transition-colors ${
              activeDoc === d.key
                ? "bg-blue-500/20 text-blue-400"
                : "text-[var(--text-secondary)] hover:bg-[var(--bg-chip)]"
            }`}
          >
            <span>{d.icon}</span>
            <span className="hidden sm:inline">{d.label}</span>
          </button>
        ))}
      </div>

      {/* 에디터 */}
      <div className="flex-1 flex flex-col min-h-0">
        <div className="flex items-center justify-between px-3 py-2 shrink-0">
          <h3 className="text-sm font-semibold text-[var(--text-primary)]">
            {doc?.icon} {doc?.label}
          </h3>
          <button
            onClick={handleSave}
            disabled={saving}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              saved
                ? "bg-[var(--bg-chip)] text-[var(--text-muted)]"
                : "bg-blue-500 text-white hover:bg-blue-600"
            }`}
          >
            {saving ? "저장 중..." : saved ? "저장됨" : "저장"}
          </button>
        </div>
        <textarea
          value={content}
          onChange={(e) => { setContent(e.target.value); setSaved(false); }}
          className="flex-1 w-full bg-[var(--bg-base)] text-[var(--text-primary)] text-sm p-4 resize-none border-none focus:outline-none font-mono leading-relaxed"
          placeholder="내용을 입력하세요..."
        />
      </div>
    </div>
  );
}
