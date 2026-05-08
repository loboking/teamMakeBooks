"use client";

import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { getToken, saveProgress } from "@/lib/auth";
import ReaderHeader from "./ReaderHeader";
import ReaderFooter from "./ReaderFooter";
import TTSPlayer from "./TTSPlayer";

type Props = {
  workId: string;
  chapterN: number;
  totalChapters: number;
  chapterTitle: string;
  body: string;
};

export default function ReaderClient({
  workId,
  chapterN,
  totalChapters,
  chapterTitle,
  body,
}: Props) {
  const [fontSize, setFontSize] = useState(18);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const handleScroll = () => {
      const pct =
        document.documentElement.scrollHeight - window.innerHeight > 0
          ? window.scrollY / (document.documentElement.scrollHeight - window.innerHeight)
          : 0;

      if (getToken()) {
        // 로그인 상태: 서버에 5초 디바운스 저장
        if (debounceRef.current) clearTimeout(debounceRef.current);
        debounceRef.current = setTimeout(() => {
          saveProgress(workId, chapterN, Math.round(pct * 100) / 100);
        }, 5000);
      } else {
        // 비로그인: localStorage 폴백
        localStorage.setItem(`progress:${workId}:${chapterN}`, String(pct));
      }
    };

    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", handleScroll);
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [workId, chapterN]);

  return (
    <div className="flex flex-col min-h-screen">
      <ReaderHeader
        title={chapterTitle}
        backHref={`/works/${workId}`}
        fontSize={fontSize}
        onFontSizeChange={setFontSize}
      />

      <main
        className="flex-1 px-5 py-6 reader-body"
        style={{ "--reader-font-size": `${fontSize}px` } as React.CSSProperties}
      >
        <ReactMarkdown
          components={{
            blockquote({ children }) {
              return (
                <blockquote className="my-4 px-4 py-3 rounded-lg bg-[var(--bg-chip)] border-l-4 border-violet-500 text-sm text-[var(--text-secondary)]">
                  {children}
                </blockquote>
              );
            },
            h1({ children }) {
              return (
                <h1 className="text-xl font-bold mt-6 mb-4 text-[var(--text-primary)]">
                  {children}
                </h1>
              );
            },
            p({ children }) {
              return (
                <p className="mb-5 leading-[1.9] text-[var(--text-primary)]">
                  {children}
                </p>
              );
            },
          }}
        >
          {body}
        </ReactMarkdown>
      </main>

      <TTSPlayer text={body} />

      <ReaderFooter
        workId={workId}
        currentN={chapterN}
        totalN={totalChapters}
      />
    </div>
  );
}
