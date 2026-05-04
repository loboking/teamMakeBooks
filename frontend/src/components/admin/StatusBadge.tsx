type Status = "합격" | "실패" | "대기" | "진행중" | "발행" | "미발행";

const STATUS_STYLES: Record<Status, string> = {
  합격: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
  실패: "bg-red-500/20 text-red-400 border-red-500/30",
  대기: "bg-amber-500/20 text-amber-400 border-amber-500/30",
  진행중: "bg-blue-500/20 text-blue-400 border-blue-500/30 animate-pulse",
  발행: "bg-purple-500/20 text-purple-400 border-purple-500/30",
  미발행: "bg-zinc-500/20 text-zinc-400 border-zinc-500/30",
};

type Props = {
  status: Status;
  size?: "sm" | "md";
};

export default function StatusBadge({ status, size = "md" }: Props) {
  const style = STATUS_STYLES[status] ?? STATUS_STYLES.대기;
  const sizeClass = size === "sm" ? "text-xs px-2 py-0.5" : "text-sm px-2.5 py-1";

  return (
    <span className={`inline-flex items-center rounded-full border font-medium ${sizeClass} ${style}`}>
      {status}
    </span>
  );
}
