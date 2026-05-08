"use client";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

const TOKEN_KEY = "tmb_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function removeToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string> | undefined),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  return fetch(`${API_BASE}${path}`, { ...init, headers });
}

export type AuthResult = { token: string; user_id: number; email: string };

export async function register(email: string, password: string): Promise<AuthResult> {
  const res = await apiFetch("/api/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) throw new Error((await res.json()).detail ?? "회원가입 실패");
  const data = await res.json();
  setToken(data.token);
  return data;
}

export async function login(email: string, password: string): Promise<AuthResult> {
  const res = await apiFetch("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) throw new Error((await res.json()).detail ?? "로그인 실패");
  const data = await res.json();
  setToken(data.token);
  return data;
}

export async function logout(): Promise<void> {
  await apiFetch("/api/auth/logout", { method: "POST" });
  removeToken();
}

export async function getMe(): Promise<{ id: number; email: string } | null> {
  if (!getToken()) return null;
  const res = await apiFetch("/api/auth/me");
  if (!res.ok) return null;
  return res.json();
}

export async function saveProgress(
  workId: string,
  chapterN: number,
  scrollPct: number,
  completed = false
): Promise<void> {
  if (!getToken()) return;
  await apiFetch(`/api/progress/${workId}/${chapterN}`, {
    method: "PUT",
    body: JSON.stringify({ scroll_pct: scrollPct, completed }),
  });
}

export async function getLastRead(): Promise<{
  work_id: string;
  chapter_n: number;
  scroll_pct: number;
} | null> {
  if (!getToken()) return null;
  const res = await apiFetch("/api/progress/continue/last");
  if (!res.ok) return null;
  const data = await res.json();
  return data.last ?? null;
}
