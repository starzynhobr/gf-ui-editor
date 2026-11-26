// Cartão flutuante da lista de Texturas: ao parar o mouse numa linha, mostra ao lado da lista a
// miniatura do .dds, o nome, as dimensões e o formato. Segue a linha sob o mouse; quem decide
// quando aparece e some é o FilesPanel (useTexturePeek).
import { AnimatePresence, motion } from 'motion/react'
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useT } from '../i18n'
import { THUMB_HEIGHT, THUMB_WIDTH, cachedPeek, fileName, loadTexturePeek, type TexturePeekData } from './peekCache'

export const PEEK_DELAY = 350
const CARD_WIDTH = THUMB_WIDTH + 24
const GAP = 10

export interface PeekTarget {
  path: string
  /** Linha sob o mouse e borda direita da lista, em coordenadas da janela. */
  rowTop: number
  rowHeight: number
  anchorRight: number
}

/** Atraso de entrada, seguir a linha e sumir: a lista só informa a linha sob o mouse (ou null). */
export function useTexturePeek(enabled: boolean) {
  const [target, setTarget] = useState<PeekTarget | null>(null)
  const timer = useRef<number | undefined>(undefined)
  const shown = useRef(false)
  const current = useRef<string | null>(null)
  const muted = useRef<string | null>(null) // linha clicada: não volta enquanto o mouse estiver nela
  shown.current = target != null

  const hide = useCallback((mute = false) => {
    window.clearTimeout(timer.current)
    if (mute) muted.current = current.current
    current.current = null
    setTarget(null)
  }, [])

  const hover = useCallback((next: PeekTarget | null) => {
    if (!enabled) return
    const path = next?.path ?? null
    if (path === current.current) return
    current.current = path
    window.clearTimeout(timer.current)
    if (!next) {
      muted.current = null
      setTarget(null)
      return
    }
    if (muted.current === path) return
    muted.current = null
    if (shown.current) setTarget(next)
    else timer.current = window.setTimeout(() => setTarget(next), PEEK_DELAY)
  }, [enabled])

  useEffect(() => () => window.clearTimeout(timer.current), [])
  useEffect(() => {
    if (!enabled) hide()
  }, [enabled, hide])
  return { target, hover, hide }
}

export function TexturePeek({ target }: { target: PeekTarget | null }) {
  return createPortal(
    <AnimatePresence>{target && <PeekCard key="peek" target={target} />}</AnimatePresence>,
    document.body,
  )
}

function PeekCard({ target }: { target: PeekTarget }) {
  const t = useT()
  const [data, setData] = useState<TexturePeekData | null | undefined>(() => cachedPeek(target.path))
  const card = useRef<HTMLDivElement>(null)
  const [height, setHeight] = useState(THUMB_HEIGHT + 80)

  useEffect(() => {
    let alive = true
    const cached = cachedPeek(target.path)
    setData(cached)
    if (!cached) void loadTexturePeek(target.path).then((value) => { if (alive) setData(value) })
    return () => {
      alive = false
    }
  }, [target.path])

  useLayoutEffect(() => {
    if (card.current) setHeight(card.current.offsetHeight)
  }, [data])

  // Centro do cartão na linha, sem sair da janela.
  const top = Math.max(8, Math.min(window.innerHeight - height - 8, target.rowTop + target.rowHeight / 2 - height / 2))
  const left = Math.min(target.anchorRight + GAP, window.innerWidth - CARD_WIDTH - 8)

  return (
    <motion.div
      ref={card}
      className="gf-texture-peek"
      data-testid="texture-peek"
      role="tooltip"
      style={{ left, width: CARD_WIDTH }}
      initial={{ opacity: 0, x: -8, scale: 0.97, top }}
      animate={{ opacity: 1, x: 0, scale: 1, top }}
      exit={{ opacity: 0, x: -6, scale: 0.97, transition: { duration: 0.12 } }}
      transition={{ type: 'spring', stiffness: 520, damping: 40, opacity: { duration: 0.14 } }}
    >
      <div className="gf-texture-peek-thumb" style={{ height: THUMB_HEIGHT }}>
        {data === undefined ? (
          <span className="gf-texture-peek-loading" aria-label={t('Carregando…')} />
        ) : data?.thumb ? (
          <Thumb bitmap={data.thumb} />
        ) : (
          <span className="px-4 text-center text-[12px] text-muted">{t('Não foi possível ler esta textura.')}</span>
        )}
      </div>
      <div className="px-3 pt-2.5 pb-3">
        <div className="truncate text-[12.5px] font-semibold text-bright" data-testid="texture-peek-name">
          {fileName(target.path)}
        </div>
        <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[11.5px]">
          {data ? (
            <>
              <span className="gf-texture-peek-tag" data-testid="texture-peek-size">{data.width} × {data.height} px</span>
              <span className="gf-texture-peek-tag is-format" data-testid="texture-peek-format">{data.format}</span>
            </>
          ) : (
            <span className="text-muted">{data === undefined ? t('Carregando…') : '—'}</span>
          )}
        </div>
      </div>
    </motion.div>
  )
}

function Thumb({ bitmap }: { bitmap: ImageBitmap }) {
  const canvas = useRef<HTMLCanvasElement>(null)
  useLayoutEffect(() => {
    const element = canvas.current
    const context = element?.getContext('2d')
    if (!element || !context) return
    element.width = bitmap.width
    element.height = bitmap.height
    try {
      context.drawImage(bitmap, 0, 0)
    } catch {
      // Miniatura descartada pelo cache (textura mudou no disco): o próximo hover recarrega.
    }
  }, [bitmap])
  return <canvas ref={canvas} className="gf-texture-peek-image" />
}
