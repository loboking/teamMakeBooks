"use client";

import { usePathname } from "next/navigation";
import Link from "next/link";
import DarkModeToggle from "@/components/DarkModeToggle";

const navItems = [
  { href: "/admin", label: "대시보드", icon: "📊" },
  { href: "/admin/chapters", label: "챕터", icon: "📖" },
  { href: "/admin/generate", label: "생성", icon: "⚙️" },
  { href: "/admin/models", label: "모델", icon: "🤖" },
  { href: "/admin/settings", label: "설정", icon: "🔧" },
];

type Props = {
  children: React.ReactNode;
  workTitle?: string;
};

export default function AdminLayout({ children, workTitle = "무등급헌터" }: Props) {
  const pathname = usePathname();

  return (
    <div className="min-h-screen bg-[var(--bg-base)] flex">
      {/* Sidebar */}
      <aside className="w-56 bg-[var(--bg-card)] border-r border-[var(--border)] flex flex-col">
        {/* Logo */}
        <div className="p-4 border-b border-[var(--border)]">
          <h1 className="font-bold text-lg text-[var(--text-primary)]">
            {workTitle}
          </h1>
          <p className="text-xs text-[var(--text-muted)] mt-1">관리자 패널</p>
        </div>

        {/* Navigation */}
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

        {/* Footer */}
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

      {/* Main content */}
      <div className="flex-1 flex flex-col">
        {/* Top bar */}
        <header className="h-14 bg-[var(--bg-card)] border-b border-[var(--border)] flex items-center justify-between px-6">
          <h2 className="font-semibold text-[var(--text-primary)]">
            {navItems.find((i) => i.href === pathname)?.label ?? "관리자"}
          </h2>
          <DarkModeToggle />
        </header>

        {/* Page content */}
        <main className="flex-1 p-6 overflow-auto">{children}</main>
      </div>
    </div>
  );
}
