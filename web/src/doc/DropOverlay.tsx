// Camada "Solte para abrir": aparece ao arrastar arquivos de fora (Explorer) sobre a janela.
// Só reage a arrastes com arquivos (dataTransfer.types tem "Files"): os arrastes internos (árvore,
// seções do painel, canvas, dnd-kit) não usam arquivos e passam direto. Quem abre é a ponte
// (drop do pywebview → drop_xml); aqui é só o aviso, que some ao sair ou soltar.
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { t, useT } from '../i18n'
import { useShell } from '../store'
import { Icon } from '../ui/Icon'

export interface DragFiles {
  /** Itens que parecem XML (tipo text/xml ou application/xml). */
  xmls: number
  /** Itens sem tipo conhecido: podem ser .xml; a ponte confere a extensão no drop. */
  unknown: number
  /** Itens que com certeza não são XML. */
  others: number
}

/** null quando o arraste não traz arquivos (arraste interno da interface). */
export function readDrag(data: DataTransfer | null | undefined): DragFiles | null {
  if (!data || !Array.from(data.types ?? []).includes('Files')) return null
  const result: DragFiles = { xmls: 0, unknown: 0, others: 0 }
  const items = Array.from(data.items ?? []).filter((item) => item.kind === 'file')
  for (const item of items) {
    if (/xml/i.test(item.type)) result.xmls += 1
    else if (!item.type) result.unknown += 1
    else result.others += 1
  }
  // Sem itens legíveis durante o arraste (alguns navegadores): trata como um possível XML.
  if (!items.length) result.unknown = 1
  return result
}

export const openable = (drag: DragFiles) => drag.xmls + drag.unknown

export function countLabel(drag: DragFiles): string {
  const count = openable(drag)
  return count === 1 ? t('1 XML') : t('{count} XMLs', { count })
}

/** Some se nenhum dragover chegar neste tempo (saiu da janela sem dragleave confiável). */
const IDLE = 180

export default function DropOverlay() {
  useT()
  const [drag, setDrag] = useState<DragFiles | null>(null)
  const hasProject = useShell((state) => !!state.shell?.project)
  const timer = useRef<number | undefined>(undefined)
  const reduced = useReducedMotion()

  useEffect(() => {
    const hide = () => {
      window.clearTimeout(timer.current)
      setDrag(null)
    }
    const over = (event: DragEvent) => {
      const files = readDrag(event.dataTransfer)
      if (!files) return
      if (event.dataTransfer && !openable(files)) event.dataTransfer.dropEffect = 'none'
      setDrag((current) =>
        current && current.xmls === files.xmls && current.unknown === files.unknown && current.others === files.others ? current : files,
      )
      window.clearTimeout(timer.current)
      timer.current = window.setTimeout(hide, IDLE)
    }
    const leave = (event: DragEvent) => {
      // Saiu da janela: relatedTarget nulo e o ponteiro fora da área visível.
      if (event.relatedTarget === null && (event.clientX <= 0 || event.clientY <= 0 ||
          event.clientX >= window.innerWidth || event.clientY >= window.innerHeight)) hide()
    }
    const drop = (event: DragEvent) => {
      const files = readDrag(event.dataTransfer)
      hide()
      if (files && !openable(files)) toast(t('Só arquivos .xml abrem no editor.'))
    }
    window.addEventListener('dragenter', over, true)
    window.addEventListener('dragover', over, true)
    window.addEventListener('dragleave', leave, true)
    window.addEventListener('drop', drop, true)
    return () => {
      window.removeEventListener('dragenter', over, true)
      window.removeEventListener('dragover', over, true)
      window.removeEventListener('dragleave', leave, true)
      window.removeEventListener('drop', drop, true)
      window.clearTimeout(timer.current)
    }
  }, [])

  const ok = drag ? openable(drag) > 0 : false
  return (
    <AnimatePresence>
      {drag && (
        <motion.div
          key="drop"
          className={`gf-drop-overlay ${ok ? '' : 'gf-drop-overlay-reject'}`}
          data-testid="drop-overlay"
          data-state={ok ? 'ok' : 'reject'}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: reduced ? 0 : 0.14 }}
          aria-live="polite"
        >
          <motion.div
            className="gf-drop-card"
            initial={reduced ? false : { scale: 0.94, y: 8 }}
            animate={{ scale: 1, y: 0 }}
            exit={reduced ? undefined : { scale: 0.97, y: 4 }}
            transition={{ type: 'spring', visualDuration: 0.28, bounce: 0.22 }}
          >
            <motion.span
              className="gf-drop-icon"
              animate={reduced || !ok ? undefined : { y: [0, -4, 0] }}
              transition={{ duration: 1.1, repeat: Infinity, ease: 'easeInOut' }}
            >
              <Icon name={ok ? 'file-import' : 'alert'} size={26} />
            </motion.span>
            {ok ? (
              <>
                <div className="gf-drop-title">{t('Solte para abrir')}</div>
                <div className="gf-drop-count" data-testid="drop-count">
                  {countLabel(drag)}
                  {drag.others > 0 && (
                    <span className="text-muted"> · {t('{count} ignorado(s): não são .xml', { count: drag.others })}</span>
                  )}
                </div>
                <div className="gf-drop-hint">
                  {hasProject
                    ? t('Abre sem mexer no projeto; depois você escolhe salvar no lugar ou importar.')
                    : t('Abre como arquivo avulso; depois você escolhe salvar no lugar ou importar para um projeto.')}
                </div>
              </>
            ) : (
              <>
                <div className="gf-drop-title">{t('Só arquivos .xml')}</div>
                <div className="gf-drop-hint">{t('Arraste os XMLs da interface do jogo (ex.: WorldMap2.xml).')}</div>
              </>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
