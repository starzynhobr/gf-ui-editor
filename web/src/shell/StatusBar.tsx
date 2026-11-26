// Barra de status: chips (projeto → UICustom, arquivos ainda não enviados, UI oficial) e a última mensagem.
import { useT } from '../i18n'
import { openOfficialReference } from '../project/flows'
import { useOfficial } from '../project/official'
import { useShell } from '../store'
import { isStandalone, shortPath } from '../doc/standalone'

export default function StatusBar() {
  const t = useT()
  const shell = useShell((state) => state.shell)
  const status = useShell((state) => state.status)
  const official = useOfficial((state) => state.status)
  const pending = shell?.pending ?? 0
  const showOfficial = Boolean(shell?.project?.game_dir && official?.has_list)
  return (
    <footer className="flex h-7 shrink-0 items-center gap-1 border-t border-border bg-chrome px-2" data-testid="statusbar">
      {shell?.project && <span className="chip">{t('{name} → UICustom', { name: shell.project.custom_name })}</span>}
      {isStandalone(shell) && (
        <span className="chip chip-standalone" title={shell?.open_path ?? ''} data-testid="standalone-status">
          {t('Avulso — {path}', { path: shortPath(shell!.open_path!) })}
        </span>
      )}
      {pending > 0 && (
        <span className="chip chip-warning">{t('{count} arquivo(s) ainda não publicados no jogo · F5', { count: pending })}</span>
      )}
      <span key={status?.id} className="status-flash selectable ml-1.5 min-w-0 flex-1 truncate text-[12px] text-muted" data-testid="status-message" title={status?.text}>
        {status?.text}
      </span>
      {showOfficial && (
        <button
          className={`chip ${official?.ready ? '' : 'chip-warning'} hover:brightness-125`}
          data-testid="official-chip"
          onClick={() => void openOfficialReference()}
        >
          {official?.ready ? t('UI oficial: guardada') : t('UI oficial: não guardada · guardar')}
        </button>
      )}
      <span className="font-mono text-[11px] text-disabled">{shell?.version}</span>
    </footer>
  )
}
