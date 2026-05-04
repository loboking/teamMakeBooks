import ModelSelector from "@/components/admin/ModelSelector";

const WORK_ID = "modern_fantasy_game_01";

export default function ModelsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold text-[var(--text-primary)] mb-1">모델 관리</h1>
        <p className="text-sm text-[var(--text-muted)]">작가, 검수, 발행에 사용할 모델을 설정합니다.</p>
      </div>

      <ModelSelector workId={WORK_ID} />
    </div>
  );
}
