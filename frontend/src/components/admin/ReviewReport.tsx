import StatusBadge from "./StatusBadge";

type Reviewer = {
  name: string;
  score: number;
  comment?: string;
};

type Props = {
  status: string;
  reviewers: Reviewer[];
};

export default function ReviewReport({ status, reviewers }: Props) {
  const overallScore = reviewers.length > 0
    ? reviewers.reduce((sum, r) => sum + r.score, 0) / reviewers.length
    : 0;

  const getScoreColor = (score: number) => {
    if (score >= 8) return "text-emerald-400";
    if (score >= 6) return "text-amber-400";
    return "text-red-400";
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">검수 리포트</h3>
        <StatusBadge status={status === "passed" ? "합격" : status === "failed" ? "실패" : "대기"} />
      </div>

      {/* Overall score */}
      {reviewers.length > 0 && (
        <div className="bg-[var(--bg-chip)] rounded-lg p-4">
          <div className="flex items-center justify-between">
            <span className="text-sm text-[var(--text-secondary)]">종합 점수</span>
            <span className={`text-2xl font-bold ${getScoreColor(overallScore)}`}>
              {overallScore.toFixed(1)}
            </span>
          </div>
        </div>
      )}

      {/* Reviewer list */}
      <div className="space-y-3">
        {reviewers.length === 0 ? (
          <p className="text-sm text-[var(--text-muted)] text-center py-4">
            검수 리포트가 없습니다.
          </p>
        ) : (
          reviewers.map((reviewer, idx) => (
            <div
              key={idx}
              className="bg-[var(--bg-card)] border border-[var(--border)] rounded-lg p-4"
            >
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-[var(--text-primary)]">
                  {reviewer.name}
                </span>
                <span className={`text-lg font-bold ${getScoreColor(reviewer.score)}`}>
                  {reviewer.score}
                </span>
              </div>
              {reviewer.comment && (
                <p className="text-sm text-[var(--text-secondary)] leading-relaxed">
                  {reviewer.comment}
                </p>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
