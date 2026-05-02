"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
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
