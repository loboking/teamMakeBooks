"use client";

import { useEffect, useRef, useState } from "react";

type Props = {
  text: string;
};

const RATE_OPTIONS = [0.75, 1.0, 1.25, 1.5, 1.75, 2.0];

export default function TTSPlayer({ text }: Props) {
  const [supported, setSupported] = useState(false);
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [voiceURI, setVoiceURI] = useState<string>("");
  const [rate, setRate] = useState<number>(1.0);
  const [playing, setPlaying] = useState(false);
  const [paused, setPaused] = useState(false);
  const [open, setOpen] = useState(false);

  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null);

  useEffect(() => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) {
      setSupported(false);
      return;
    }
    setSupported(true);

    const loadVoices = () => {
      const all = window.speechSynthesis.getVoices();
      const ko = all.filter((v) => v.lang?.startsWith("ko"));
      setVoices(ko.length > 0 ? ko : all);
      const stored = localStorage.getItem("tts.voiceURI");
      if (stored && all.some((v) => v.voiceURI === stored)) {
        setVoiceURI(stored);
      } else if (ko.length > 0) {
        setVoiceURI(ko[0].voiceURI);
      } else if (all.length > 0) {
        setVoiceURI(all[0].voiceURI);
      }
    };
    loadVoices();
    window.speechSynthesis.onvoiceschanged = loadVoices;

    const storedRate = parseFloat(localStorage.getItem("tts.rate") || "1");
    if (!Number.isNaN(storedRate)) setRate(storedRate);

    return () => {
      window.speechSynthesis.cancel();
    };
  }, []);

  useEffect(() => {
    if (voiceURI) localStorage.setItem("tts.voiceURI", voiceURI);
  }, [voiceURI]);

  useEffect(() => {
    localStorage.setItem("tts.rate", String(rate));
  }, [rate]);

  function plainText(markdown: string): string {
    // 간단한 markdown → plain text. AI 배지(blockquote), 제목, 코드블록 제거.
    return markdown
      .replace(/```[\s\S]*?```/g, "")
      .replace(/^>.*$/gm, "")
      .replace(/^#+\s.*$/gm, "")
      .replace(/!\[.*?\]\(.*?\)/g, "")
      .replace(/\[(.*?)\]\(.*?\)/g, "$1")
      .replace(/[*_`~]/g, "")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
  }

  function speak() {
    if (!supported) return;
    const synth = window.speechSynthesis;
    if (paused) {
      synth.resume();
      setPaused(false);
      setPlaying(true);
      return;
    }
    synth.cancel();
    const u = new SpeechSynthesisUtterance(plainText(text));
    const v = voices.find((vv) => vv.voiceURI === voiceURI);
    if (v) u.voice = v;
    u.rate = rate;
    u.lang = v?.lang ?? "ko-KR";
    u.onend = () => {
      setPlaying(false);
      setPaused(false);
    };
    u.onerror = () => {
      setPlaying(false);
      setPaused(false);
    };
    utteranceRef.current = u;
    synth.speak(u);
    setPlaying(true);
    setPaused(false);
  }

  function pause() {
    if (!supported) return;
    window.speechSynthesis.pause();
    setPaused(true);
    setPlaying(false);
  }

  function stop() {
    if (!supported) return;
    window.speechSynthesis.cancel();
    setPlaying(false);
    setPaused(false);
  }

  if (!supported) return null;

  return (
    <>
      {/* 하단 우측 floating 버튼 */}
      <button
        type="button"
        aria-label={playing ? "TTS 일시정지" : "TTS 재생"}
        onClick={() => {
          if (playing) {
            pause();
          } else {
            speak();
          }
          setOpen(true);
        }}
        className="fixed bottom-24 right-5 z-30 w-14 h-14 rounded-full bg-violet-500 hover:bg-violet-600 active:scale-95 text-white shadow-lg flex items-center justify-center transition"
      >
        {playing ? (
          <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor">
            <rect x="6" y="5" width="4" height="14" rx="1" />
            <rect x="14" y="5" width="4" height="14" rx="1" />
          </svg>
        ) : (
          <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor">
            <path d="M8 5v14l11-7-11-7z" />
          </svg>
        )}
      </button>

      {/* 컨트롤 패널 */}
      {open && (
        <div className="fixed bottom-44 right-5 z-30 w-64 p-4 rounded-xl bg-[var(--bg-card)] border border-[var(--border)] shadow-xl text-sm">
          <div className="flex items-center justify-between mb-3">
            <span className="font-semibold text-[var(--text-primary)]">🔊 음성 재생</span>
            <button
              type="button"
              aria-label="패널 닫기"
              onClick={() => setOpen(false)}
              className="text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            >
              ✕
            </button>
          </div>

          <div className="flex gap-2 mb-3">
            <button
              type="button"
              onClick={speak}
              disabled={playing}
              className="flex-1 py-2 rounded-md bg-violet-500 hover:bg-violet-600 disabled:bg-violet-500/40 text-white font-medium transition"
            >
              {paused ? "이어서" : "재생"}
            </button>
            <button
              type="button"
              onClick={stop}
              className="flex-1 py-2 rounded-md bg-[var(--bg-chip)] hover:bg-[var(--bg-chip-hover)] text-[var(--text-primary)] font-medium transition"
            >
              정지
            </button>
          </div>

          <label className="block mb-3">
            <div className="text-xs mb-1 text-[var(--text-secondary)]">속도 ({rate.toFixed(2)}x)</div>
            <div className="flex gap-1">
              {RATE_OPTIONS.map((r) => (
                <button
                  key={r}
                  type="button"
                  onClick={() => setRate(r)}
                  className={`flex-1 py-1 rounded text-xs transition ${
                    Math.abs(rate - r) < 0.01
                      ? "bg-violet-500 text-white"
                      : "bg-[var(--bg-chip)] text-[var(--text-secondary)] hover:bg-[var(--bg-chip-hover)]"
                  }`}
                >
                  {r}x
                </button>
              ))}
            </div>
          </label>

          {voices.length > 0 && (
            <label className="block">
              <div className="text-xs mb-1 text-[var(--text-secondary)]">음성</div>
              <select
                value={voiceURI}
                onChange={(e) => setVoiceURI(e.target.value)}
                className="w-full py-1.5 px-2 rounded bg-[var(--bg-chip)] text-[var(--text-primary)] text-xs border border-[var(--border)]"
              >
                {voices.map((v) => (
                  <option key={v.voiceURI} value={v.voiceURI}>
                    {v.name} ({v.lang})
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
      )}
    </>
  );
}
