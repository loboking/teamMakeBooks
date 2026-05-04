"use client";

import { useState, useEffect } from "react";
import { usePathname } from "next/navigation";
import Link from "next/link";
import { AdminContext } from "@/lib/admin";
import DarkModeToggle from "@/components/DarkModeToggle";

const navItems = [
  { href: "/admin", label: "대시보드", icon: "📊" },
  { href: "/admin/chapters", label: "챕터", icon: "📖" },
  { href: "/admin/generate", label: "생성", icon: "⚙️" },
  { href: "/admin/models", label: "모델", icon: "🤖" },
  { href: "/admin/prep", label: "준비", icon: "📝" },
  { href: "/admin/validate", label: "검증", icon: "✅" },
  { href: "/admin/settings", label: "설정", icon: "🔧" },
];

type Props = {
  children: React.ReactNode;
  workTitle?: string;
};

export default function AdminLayout({ children }: Props) {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const [works, setWorks] = useState<{ work_id: string; title: string }[]>([]);
  const [selectedWork, setSelectedWork] = useState("modern_fantasy_game_01");

  useEffect(() => {
    fetch("/api/works")
      .then((r) => r.json())
      .then((d) => setWorks(d.works || []))
      .catch(() => {});
  }, []);

  const currentPage = navItems.find((i) => i.href === pathname)?.label ?? "관리자";

  return (
    <AdminContext.Provider value={{ selectedWork, setSelectedWork }}>
    <div className="min-h-screen bg-[var(--bg-base)] flex flex-col md:flex-row">
      {/* 모바일 상단바 */}
      <header className="md:hidden h-12 bg-[var(--bg-card)] border-b border-[var(--border)] flex items-center justify-between px-3 gap-2 shrink-0">
        <select
          value={selectedWork}
          onChange={(e) => setSelectedWork(e.target.value)}
          className="flex-1 bg-[var(--bg-base)] border border-[var(--border)] rounded-lg px-2 py-1.5 text-xs text-[var(--text-primary)] max-w-[140px]"
        >
          {works.map((w) => (
            <option key={w.work_id} value={w.work_id}>{w.title}</option>
          ))}
        </select>
        <div className="flex items-center gap-2">
          <DarkModeToggle />
          <button
            onClick={() => setMenuOpen(!menuOpen)}
            className="p-1 text-[var(--text-secondary)]"
          >
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              {menuOpen ? (
                <path d="M18 6L6 18M6 6l12 12" />
              ) : (
                <><path d="M3 12h18M3 6h18M3 18h18" /></>
              )}
            </svg>
          </button>
        </div>
      </header>

      {/* 모바일 드롭다운 메뉴 */}
      {menuOpen && (
        <nav className="md:hidden bg-[var(--bg-card)] border-b border-[var(--border)] p-2 space-y-1 shrink-0">
          {navItems.map((item) => {
            const isActive = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setMenuOpen(false)}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors ${
                  isActive
                    ? "bg-blue-500/20 text-blue-400"
                    : "text-[var(--text-secondary)] hover:bg-[var(--bg-chip)]"
                }`}
              >
                <span className="text-lg">{item.icon}</span>
                <span className="text-sm font-medium">{item.label}</span>
              </Link>
            );
          })}
          <a
            href="/"
            className="flex items-center gap-2 px-3 py-2 text-sm text-[var(--text-muted)]"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M19 12H5M12 19l-7-7 7-7" />
            </svg>
            사이트로
          </a>
        </nav>
      )}

      {/* 데스크톱 사이드바 */}
      <aside className="hidden md:flex w-52 lg:w-56 bg-[var(--bg-card)] border-r border-[var(--border)] flex-col shrink-0">
        <div className="p-4 border-b border-[var(--border)]">
          <select
            value={selectedWork}
            onChange={(e) => setSelectedWork(e.target.value)}
            className="w-full bg-[var(--bg-base)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm text-[var(--text-primary)]"
          >
            {works.map((w) => (
              <option key={w.work_id} value={w.work_id}>{w.title}</option>
            ))}
          </select>
          <button
            onClick={() => {
              const title = prompt("새 작품 제목:");
              if (title) {
                fetch("/api/works", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ title }),
                })
                  .then((r) => r.json())
                  .then((d) => {
                    if (d.work_id) { setSelectedWork(d.work_id); setWorks((prev) => [...prev, { work_id: d.work_id, title: d.title }]); }
                  });
              }
            }}
            className="mt-2 w-full text-xs text-center py-1.5 rounded-lg bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 transition-colors"
          >
            + 새 작품
          </button>
        </div>
        <nav className="flex-1 p-2 space-y-1">
          {navItems.map((item) => {
            const isActive = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors ${
                  isActive
                    ? "bg-blue-500/20 text-blue-400"
                    : "text-[var(--text-secondary)] hover:bg-[var(--bg-chip)] hover:text-[var(--text-primary)]"
                }`}
              >
                <span className="text-lg">{item.icon}</span>
                <span className="text-sm font-medium">{item.label}</span>
              </Link>
            );
          })}
        </nav>
        <div className="p-4 border-t border-[var(--border)]">
          <a
            href="/"
            className="flex items-center gap-2 text-sm text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M19 12H5M12 19l-7-7 7-7" />
            </svg>
            사이트로
          </a>
        </div>
      </aside>

      {/* 메인 콘텐츠 */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* 데스크톱 상단바 */}
        <header className="hidden md:flex h-14 bg-[var(--bg-card)] border-b border-[var(--border)] items-center justify-between px-6 shrink-0">
          <h2 className="font-semibold text-[var(--text-primary)]">{currentPage}</h2>
          <DarkModeToggle />
        </header>
        <main className="flex-1 p-3 md:p-6 overflow-auto">{children}</main>
      </div>
    </div>
    </AdminContext.Provider>
  );
}
