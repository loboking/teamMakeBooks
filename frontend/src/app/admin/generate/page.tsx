import ScheduleControl from "@/components/admin/ScheduleControl";
import PipelineStatus from "@/components/admin/PipelineStatus";

const WORK_ID = "modern_fantasy_game_01";

export default function GeneratePage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold text-[var(--text-primary)] mb-1">생성 관리</h1>
        <p className="text-sm text-[var(--text-muted)]">챕터 자동 생성 스케줄을 관리합니다.</p>
      </div>

      <ScheduleControl workId={WORK_ID} />
      <PipelineStatus workId={WORK_ID} />
    </div>
  );
}
