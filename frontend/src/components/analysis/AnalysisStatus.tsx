import type { AnalysisRun } from '@/lib/api'

const labels: Record<AnalysisRun['status'], string> = {
  queued: '正在整理来源与生成分析…',
  running: '正在整理来源与生成分析…',
  completed: '报告已就绪',
  failed: '生成分析失败',
}

export function AnalysisStatus({ run }: { run?: AnalysisRun | null }) {
  if (!run) return null

  const failed = run.status === 'failed'
  return (
    <p role={failed ? 'alert' : 'status'} aria-live="polite" className={failed ? 'text-sm text-danger' : 'text-sm text-secondary'}>
      {labels[run.status]}
    </p>
  )
}
