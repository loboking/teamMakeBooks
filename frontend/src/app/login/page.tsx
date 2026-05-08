"use client";

import { useState } from "react";
import { login, register } from "@/lib/auth";

export default function LoginPage() {
  const [tab, setTab] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      if (tab === "login") {
        await login(email, password);
      } else {
        await register(email, password);
      }
      window.location.href = "/";
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "오류가 발생했습니다");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-[400px] mx-auto min-h-screen flex flex-col justify-center px-6">
      <h1 className="text-xl font-bold text-center mb-8 text-[var(--text-primary)]">
        teamMakeBooks
      </h1>

      {/* 탭 */}
      <div className="flex border-b border-[var(--border)] mb-6">
        {(["login", "register"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`flex-1 py-2 text-sm font-medium transition-colors ${
              tab === t
                ? "border-b-2 border-violet-500 text-[var(--text-primary)]"
                : "text-[var(--text-muted)]"
            }`}
          >
            {t === "login" ? "로그인" : "회원가입"}
          </button>
        ))}
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <input
          type="email"
          required
          placeholder="이메일"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="px-4 py-3 rounded-lg border border-[var(--border)] bg-[var(--bg-chip)] text-[var(--text-primary)] text-sm outline-none focus:ring-2 focus:ring-violet-500"
        />
        <input
          type="password"
          required
          placeholder="비밀번호"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="px-4 py-3 rounded-lg border border-[var(--border)] bg-[var(--bg-chip)] text-[var(--text-primary)] text-sm outline-none focus:ring-2 focus:ring-violet-500"
        />
        {error && <p className="text-red-500 text-xs">{error}</p>}
        <button
          type="submit"
          disabled={loading}
          className="py-3 rounded-lg bg-violet-600 text-white font-medium text-sm disabled:opacity-50 hover:bg-violet-700 transition-colors"
        >
          {loading ? "처리 중..." : tab === "login" ? "로그인" : "회원가입"}
        </button>
      </form>
    </div>
  );
}
