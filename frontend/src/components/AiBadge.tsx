type AiBadgeSize = "sm" | "md" | "lg";

export default function AiBadge({ size = "md" }: { size?: AiBadgeSize }) {
  const sizeClass = {
    sm: "text-xs px-1.5 py-0.5",
    md: "text-sm px-2 py-1",
    lg: "text-base px-3 py-1.5",
  }[size];

  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md bg-violet-900/40 text-violet-300 font-medium border border-violet-700/50 ${sizeClass}`}
    >
      AI 생성
    </span>
  );
}
