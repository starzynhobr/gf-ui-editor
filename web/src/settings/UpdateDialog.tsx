// Atualização disponível, como o WhatsNewDialog da clássica com current_version: versão atual
// → nova, notas traduzidas (inclusive as das versões puladas) e Pular / Depois / Atualizar.
import { t, useT } from '../i18n'
import { Modal, openDialog } from '../ui/dialogs'
import { ReleaseNotes } from './ReleaseNotes'
import type { UpdateOffer } from './settingsApi'
import './settings.css'

export type UpdateChoice = 'update' | 'skip' | 'later'

function UpdateDialog({ offer, finish }: { offer: UpdateOffer; finish: (choice: UpdateChoice) => void }) {
  useT()
  const single = offer.releases.length === 1 && !offer.grouped ? offer.releases[0] : null
  const safety = !offer.can_install
    ? t('Você está rodando pelo código-fonte; a página da release será aberta.')
    : offer.verified
      ? t('Seu trabalho fica salvo antes de atualizar. O download é conferido por SHA-256 antes de instalar, e nada é instalado sem a sua confirmação.')
      : t('Seu trabalho fica salvo antes de atualizar. O download vem direto da release no GitHub por HTTPS, e nada é instalado sem a sua confirmação.')
  return (
    <Modal
      title={t('Atualização disponível')}
      width={offer.releases.length > 1 ? 800 : 640}
      onClose={() => finish('later')}
      footer={
        <div className="flex w-full items-center gap-2" data-testid="update-dialog-footer">
          <button className="btn btn-ghost" onClick={() => finish('skip')}>
            {t('Pular esta versão')}
          </button>
          <div className="flex-1" />
          <button className="btn" onClick={() => finish('later')}>
            {t('Depois')}
          </button>
          <button className="btn btn-primary" autoFocus onClick={() => finish('update')}>
            {offer.can_install ? t('Baixar e instalar') : t('Abrir página da release')}
          </button>
        </div>
      }
    >
      <div className="space-y-4" data-testid="update-dialog">
        <div className="space-y-2">
          <div className="flex items-center gap-2 font-mono text-[12px] text-muted">
            <span>{offer.current}</span>
            <span>→</span>
            <span className="gf-version-chip">{offer.version}</span>
            <div className="flex-1" />
            {single?.date && <span>{single.date}</span>}
          </div>
          <div className="text-[18px] font-semibold text-bright">
            {offer.grouped
              ? t('O que chegou desde a {version}', { version: offer.current })
              : t('O que chegou na {version}', { version: offer.version })}
          </div>
        </div>
        {offer.releases.length ? (
          <ReleaseNotes releases={offer.releases} showVersion={offer.grouped} />
        ) : (
          <div className="whitespace-pre-wrap text-text">{offer.fallback_text || t('Sem notas para esta versão.')}</div>
        )}
        <div className="gf-note-box">{safety}</div>
      </div>
    </Modal>
  )
}

/** Mostra a oferta e devolve a escolha (fechar = Depois). */
export function openUpdateDialog(offer: UpdateOffer): Promise<UpdateChoice> {
  return new Promise((resolve) => {
    const close = openDialog(() => (
      <UpdateDialog
        offer={offer}
        finish={(choice) => {
          close()
          resolve(choice)
        }}
      />
    ))
  })
}
