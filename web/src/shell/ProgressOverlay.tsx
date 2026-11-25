// Progresso de operações longas (criar projeto, enviar, exportar), como o _run_with_progress.
import { useEffect } from 'react'
import { on } from '../bridge'
import { useShell } from '../store'

export default function ProgressOverlay() {
  const progress = useShell((state) => state.progress)
  useEffect(
    () =>
      on('progress', (payload) => {
        const { done, total } = payload as { done: number; total: number }
        const current = useShell.getState().progress
        if (current) useShell.setState({ progress: { ...current, done, total } })
      }),
    [],
  )
  if (!progress) return null
  const percent = progress.total ? Math.round((progress.done / progress.total) * 100) : null
  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/45" data-testid="progress">
      <div className="w-[420px] rounded-xl border border-border-strong bg-panel px-5 py-4 shadow-2xl shadow-black/50">
        <div className="mb-3 text-text">{progress.label}</div>
        <div className="h-1.5 overflow-hidden rounded-full bg-input">
          {percent == null ? (
            <div className="h-full w-1/3 animate-[slide_1.1s_ease-in-out_infinite] rounded-full bg-accent" />
          ) : (
            <div className="h-full rounded-full bg-accent transition-[width] duration-100" style={{ width: `${percent}%` }} />
          )}
        </div>
        {progress.total > 0 && (
          <div className="mt-2 text-right font-mono text-[11px] text-muted">
            {progress.done} / {progress.total}
          </div>
        )}
      </div>
    </div>
  )
}
