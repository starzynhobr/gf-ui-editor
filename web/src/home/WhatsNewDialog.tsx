// Novidades desta versão (release-notes.json embutido), como o WhatsNewDialog da clássica.
// "Ver todas" traz também o histórico embutido, com a linha do tempo das versões.
//
// Depois de atualizar, abrem sozinhas uma vez (startWhatsNew, antes dos outros avisos). Aberta
// assim, clicar fora não fecha (só Fechar, o X ou Esc) e, ao fechar, o diálogo voa até a pílula
// "Novidades ×" da barra; clicar na pílula reabre com o voo inverso (home/flight.ts).
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { api, type ReleaseNote } from '../api'
import { call } from '../bridge'
import { t, useT } from '../i18n'
import { ReleaseNotes, type Release } from '../settings/ReleaseNotes'
import { backToClassic } from '../settings/interfaceSwitch'
import { Modal, openDialog } from '../ui/dialogs'
import { flyIn, flyOut, landingRect, nextFrame } from './flight'
import { markClosed, notesClosed, notesOpened, useWhatsNew, type WhatsNewMode } from './whatsNew'

function WhatsNew({ mode, source, onDone }: { mode: WhatsNewMode; source: DOMRect | null; onDone: () => void }) {
  useT()
  const [notes, setNotes] = useState<ReleaseNote | null>(null)
  const [history, setHistory] = useState<Release[] | null>(null)
  const [all, setAll] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  const overlay = useRef<HTMLDivElement>(null)
  const closing = useRef(false)
  useEffect(() => {
    void api.whatsNew().then(setNotes, () => undefined)
    // O histórico já vem para saber se "Ver todas" tem o que mostrar (senão o botão nem aparece).
    void call<{ releases: Release[] }>('release_history').then((data) => setHistory(data.releases), () => setHistory([]))
  }, [])
  // Pela pílula: cresce a partir dela.
  useLayoutEffect(() => {
    if (mode === 'pill' && box.current) void flyIn(box.current, overlay.current, source)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- só na abertura
  }, [])

  const close = useCallback(async () => {
    if (closing.current) return
    closing.current = true
    const toPill = mode !== 'manual' || useWhatsNew.getState().pill
    if (mode !== 'manual') markClosed()
    if (toPill && box.current) {
      await nextFrame() // a pílula entra na barra (ainda invisível) para ser medida
      await flyOut(box.current, overlay.current, landingRect(), () => useWhatsNew.setState({ covering: false }))
    }
    useWhatsNew.setState({ covering: false })
    onDone()
  }, [mode, onDone])

  const releases: Release[] = all && history ? history : notes ? [notes] : []
  const hasMore = (history?.length ?? 0) > 1
  return (
    <Modal
      title={t('Novidades')}
      width={all ? 800 : 640}
      onClose={() => void close()}
      boxRef={box}
      overlayRef={overlay}
      animated={mode !== 'pill'}
      footer={
        <button className="btn btn-primary" data-testid="whats-new-close" onClick={() => void close()}>
          {t('Fechar')}
        </button>
      }
    >
      {notes && (
        <div className="space-y-3" data-testid="whats-new" data-mode={mode}>
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
          <ReleaseNotes
            key={all ? 'all' : 'current'}
            releases={releases}
            showVersion={all}
            onBackToClassic={() => void backToClassic(mode !== 'manual' ? markClosed : undefined)}
          />
        </div>
      )}
    </Modal>
  )
}

/**
 * Abre as Novidades. `auto`: aberta sozinha depois de atualizar; `pill`: pela pílula da barra
 * (`source` é o retângulo dela); `manual`: engrenagem, Configurações, Ctrl+K, tela inicial.
 * Resolve quando o diálogo fecha.
 */
export function showWhatsNew(mode: WhatsNewMode = 'manual', source: DOMRect | null = null): Promise<void> {
  return new Promise((resolve) => {
    if (mode !== 'manual' || useWhatsNew.getState().pill) useWhatsNew.setState({ covering: true })
    notesOpened()
    openDialog((close) => (
      <WhatsNew
        mode={mode}
        source={source}
        onDone={() => {
          close()
          notesClosed()
          resolve()
        }}
      />
    ))
  })
}

/** Abre as Novidades sem esperar (menus, botões). */
export function openWhatsNew(mode: WhatsNewMode = 'manual', source: DOMRect | null = null): void {
  void showWhatsNew(mode, source)
}

/**
 * Ao iniciar, antes de qualquer outro aviso: abre sozinha se o Python pedir e espera fechar.
 * Devolve true se abriu.
 */
export async function startWhatsNew(): Promise<boolean> {
  let state
  try {
    state = await api.whatsNewState()
  } catch {
    return false
  }
  if (!state.auto_open) {
    useWhatsNew.setState({ pill: state.pill })
    return false
  }
  useWhatsNew.setState({ hold: true })
  try {
    await showWhatsNew('auto')
  } finally {
    useWhatsNew.setState({ hold: false })
  }
  return true
}
