// Novidades desta versão (release-notes.json embutido), como o WhatsNewDialog da clássica.
// "Ver todas" traz também o histórico embutido, com a linha do tempo das versões.
import { useEffect, useState } from 'react'
import { api } from '../api'
import { call } from '../bridge'
import { t, useT } from '../i18n'
import { ReleaseNotes, type Release } from '../settings/ReleaseNotes'
import { Modal, openDialog } from '../ui/dialogs'

type Notes = Awaited<ReturnType<typeof api.whatsNew>>

function WhatsNew({ onClose }: { onClose: () => void }) {
  useT()
  const [notes, setNotes] = useState<Notes | null>(null)
  const [history, setHistory] = useState<Release[] | null>(null)
  const [all, setAll] = useState(false)
  useEffect(() => {
    void api.whatsNew().then(setNotes)
    // O histórico já vem para saber se "Ver todas" tem o que mostrar (senão o botão nem aparece).
    void call<{ releases: Release[] }>('release_history').then((data) => setHistory(data.releases), () => setHistory([]))
  }, [])
  const releases: Release[] = all && history ? history : notes ? [notes] : []
  const hasMore = (history?.length ?? 0) > 1
  return (
    <Modal
      title={t('Novidades')}
      width={all ? 800 : 640}
      onClose={onClose}
      footer={
        <button className="btn btn-primary" onClick={onClose}>
          {t('Fechar')}
        </button>
      }
    >
      {notes && (
        <div className="space-y-3" data-testid="whats-new">
          <div className="flex items-center gap-2 text-muted">
            <span className="gf-version-chip font-mono text-[12px]">{all ? t('{count} versões', { count: releases.length }) : notes.version}</span>
            {!all && notes.date && <span className="text-[12px]">{notes.date}</span>}
            <div className="flex-1" />
            {hasMore && (
              <button className="link text-[12px]" data-testid="whats-new-all" onClick={() => setAll(!all)}>
                {all ? t('Só esta versão') : t('Ver todas as versões')}
              </button>
            )}
          </div>
          <ReleaseNotes key={all ? 'all' : 'current'} releases={releases} showVersion={all} />
        </div>
      )}
    </Modal>
  )
}

export function openWhatsNew(): void {
  openDialog((close) => <WhatsNew onClose={close} />)
}
