// Avisos acima do canvas, como os da clássica: controles novos que a atualização do jogo trouxe
// para o XML aberto, UI oficial não guardada e as cópias que o F5 guardou de arquivos editados fora.
import type { ReactNode } from 'react'
import { useT } from '../i18n'
import { useShell } from '../store'
import { Icon } from '../ui/Icon'
import { dismissOfficialBanner, openOfficialCompare, openOfficialReference, showGameBackups } from './flows'
import { officialKey, useOfficial } from './official'
import { acknowledgeTextUpdates, useTextUpdates } from './textUpdates'
import { publishToGame } from '../actions'
import { useListAnimation } from '../ui/animate'

function Banner({ children, action, onAction, onDismiss, testId }: { children: ReactNode; action: string; onAction: () => void; onDismiss: () => void; testId: string }) {
  const t = useT()
  return (
    <div className="flex items-center gap-2.5 border-b border-warning-border bg-warning-bg px-3.5 py-2 text-[12.5px] text-warning" data-testid={testId}>
      <Icon name="info" size={17} className="text-gold" />
      <div className="min-w-0 flex-1 leading-snug">{children}</div>
      <button className="btn h-7 border-warning-border bg-transparent text-warning" onClick={onAction}>
        {action}
      </button>
      <button className="icon-button text-warning" title={t('Dispensar')} aria-label={t('Dispensar')} onClick={onDismiss}>
        <Icon name="x" size={15} />
      </button>
    </div>
  )
}

export default function Banners() {
  const animate = useListAnimation()
  const t = useT()
  const shell = useShell((state) => state.shell)
  const { status, diffs, dismissed, referenceDismissed, gameBackups } = useOfficial()
  const key = officialKey(shell?.project?.ui_dir, shell?.open_path)
  const diff = key ? diffs[key] : undefined
  const showOfficial = Boolean(diff?.new_ids.length) && key != null && !dismissed.includes(key)
  const showReference = Boolean(status?.has_list && !status.ready && !referenceDismissed)
  const { report, dismissed: textsDismissed } = useTextUpdates()
  const textUpdate = report?.update
  const reverted = report?.reverted.length ?? 0
  const showTexts = Boolean(report && !textsDismissed && (textUpdate || reverted))
  const textParts = [
    textUpdate
      ? t('O jogo atualizou os textos: {new} ID(s) novo(s) e {changed} texto(s) oficial(is) alterado(s).', {
          new: textUpdate.new_ids,
          changed: textUpdate.changed_texts,
        })
      : '',
    reverted ? t('{count} edição(ões) de texto deste projeto foram desfeitas pela atualização: envie de novo (F5).', { count: reverted }) : '',
    report?.official_changed.length
      ? t('{count} texto(s) editado(s) mudaram no jogo por baixo da edição: confira antes de enviar.', { count: report.official_changed.length })
      : '',
  ].filter(Boolean)
  return (
    <div ref={animate}>
      {showTexts && (
        <Banner
          testId="text-updates-banner"
          action={reverted ? t('Reenviar edições') : t('Entendi')}
          onAction={() => void (reverted ? publishToGame().then(() => acknowledgeTextUpdates()) : acknowledgeTextUpdates())}
          onDismiss={() => void acknowledgeTextUpdates()}
        >
          {textParts.join(' ')}
        </Banner>
      )}
      {showOfficial && diff && (
        <Banner testId="official-banner" action={t('Ver e adicionar')} onAction={() => void openOfficialCompare()} onDismiss={dismissOfficialBanner}>
          {t('A atualização do jogo trouxe {count} controle(s) que este arquivo não tem ({ids}).', {
            count: diff.new_ids.length,
            ids: diff.new_ids.slice(0, 6).join(', ') + (diff.new_ids.length > 6 ? '…' : ''),
          })}
        </Banner>
      )}
      {showReference && (
        <Banner
          testId="reference-banner"
          action={t('Guardar UI oficial')}
          onAction={() => void openOfficialReference()}
          onDismiss={() => useOfficial.setState({ referenceDismissed: true })}
        >
          {t('A UI oficial desta versão do jogo não está guardada: sem ela o editor não avisa quando uma atualização traz controles novos.')}
        </Banner>
      )}
      {gameBackups > 0 && (
        <Banner testId="backup-banner" action={t('Ver')} onAction={() => void showGameBackups()} onDismiss={() => useOfficial.setState({ gameBackups: 0 })}>
          {t('{count} arquivo(s) da pasta do jogo estavam diferentes do que o editor enviou (editados fora?) e foram substituídos pelo envio; a versão de antes ficou guardada.', {
            count: gameBackups,
          })}
        </Banner>
      )}
    </div>
  )
}
