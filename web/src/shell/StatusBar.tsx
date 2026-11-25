// Barra de status: chips (projeto → UICustom, arquivos ainda não enviados) e a última mensagem.
import { useT } from '../i18n'
import { useShell } from '../store'

export default function StatusBar() {
  const t = useT()
  const shell = useShell((state) => state.shell)
  const status = useShell((state) => state.status)
  const pending = shell?.pending ?? 0
  return (
    <footer className="flex h-7 shrink-0 items-center gap-1 border-t border-border bg-chrome px-2" data-testid="statusbar">
      {shell?.project && <span className="chip">{t('{name} → UICustom', { name: shell.project.custom_name })}</span>}
      {pending > 0 && (
        <span className="chip chip-warning">{t('{count} arquivo(s) ainda não publicados no jogo · F5', { count: pending })}</span>
      )}
      <span className="selectable ml-1.5 min-w-0 flex-1 truncate text-[12px] text-muted" data-testid="status-message" title={status?.text}>
        {status?.text}
      </span>
      <span className="font-mono text-[11px] text-disabled">{shell?.version}</span>
    </footer>
  )
}
