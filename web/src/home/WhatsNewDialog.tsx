// Novidades desta versão (release-notes.json embutido), como o WhatsNewDialog da clássica.
import { useEffect, useState } from 'react'
import { api } from '../api'
import { t, useT } from '../i18n'
import { Modal, openDialog } from '../ui/dialogs'

type Notes = Awaited<ReturnType<typeof api.whatsNew>>

function WhatsNew({ onClose }: { onClose: () => void }) {
  useT()
  const [notes, setNotes] = useState<Notes | null>(null)
  useEffect(() => {
    void api.whatsNew().then(setNotes)
  }, [])
  const headings: Record<string, [string, string]> = {
    new: [t('NOVO'), 'text-success'],
    improved: [t('MELHORADO'), 'text-accent-text'],
    fixed: [t('CORRIGIDO'), 'text-gold'],
  }
  return (
    <Modal
      title={t('Novidades')}
      width={560}
      onClose={onClose}
      footer={
        <button className="btn btn-primary" onClick={onClose}>
          {t('Fechar')}
        </button>
      }
    >
      {notes && (
        <div className="space-y-4">
          <div className="text-muted">
            {notes.version}
            {notes.date ? ` · ${notes.date}` : ''}
          </div>
          {(['new', 'improved', 'fixed'] as const).map((section) =>
            notes.sections[section].length ? (
              <section key={section} className="space-y-2">
                <div className={`section-label ${headings[section][1]}`}>{headings[section][0]}</div>
                {notes.sections[section].map(([title, text]) => (
                  <div key={title} className="leading-relaxed">
                    <span className="font-semibold text-bright">{title}</span> <span className="text-text">{text}</span>
                  </div>
                ))}
              </section>
            ) : null,
          )}
        </div>
      )}
    </Modal>
  )
}

export function openWhatsNew(): void {
  openDialog((close) => <WhatsNew onClose={close} />)
}
