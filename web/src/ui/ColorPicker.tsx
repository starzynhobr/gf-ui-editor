// Seletor de cor no tema do app (react-colorful), no lugar do diálogo de cor do Windows.
// Mexer no quadro só mostra a prévia; grava uma vez ao fechar (um passo de desfazer), como
// o "change" do seletor nativo. Um <input type="color"> escondido continua lá para scripts e
// testes (mudar o valor dele + evento change também grava).
import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useRef, useState } from 'react'
import { HexColorInput, HexColorPicker } from 'react-colorful'

const SWATCHES = ['#ffffff', '#000000', '#ffff00', '#ff0000', '#00ff00', '#00ffff', '#ff9900', '#c0c0c0']

export function ColorPicker({
  value,
  disabled,
  title,
  name,
  onCommit,
}: {
  value: string
  disabled?: boolean
  title?: string
  name?: string
  onCommit: (hex: string) => void
}) {
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState(value)
  const box = useRef<HTMLDivElement>(null)
  const hidden = useRef<HTMLInputElement>(null)
  const commit = useRef(onCommit)
  commit.current = onCommit

  useEffect(() => setDraft(value), [value])
  useEffect(() => {
    const input = hidden.current
    if (!input) return
    const listener = () => commit.current(input.value)
    input.addEventListener('change', listener)
    return () => input.removeEventListener('change', listener)
  }, [])
  useEffect(() => {
    if (hidden.current) hidden.current.value = value
  }, [value])

  const close = () => {
    setOpen(false)
    if (draft.toLowerCase() !== value.toLowerCase()) commit.current(draft)
  }
  useEffect(() => {
    if (!open) return
    const outside = (event: MouseEvent) => {
      const target = event.target
      if (box.current && !(target instanceof Node && box.current.contains(target))) close()
    }
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setDraft(value)
        setOpen(false)
      }
      if (event.key === 'Enter') close()
    }
    window.addEventListener('mousedown', outside)
    window.addEventListener('keydown', escape)
    return () => {
      window.removeEventListener('mousedown', outside)
      window.removeEventListener('keydown', escape)
    }
  })

  return (
    <div ref={box} className="relative">
      <button
        type="button"
        className="field flex h-7 w-full items-center gap-2 font-mono text-[12px]"
        disabled={disabled}
        title={title}
        data-testid="color-button"
        onClick={() => (open ? close() : setOpen(true))}
      >
        <span className="h-3.5 w-3.5 rounded-sm border border-border-strong" style={{ background: open ? draft : value }} />
        {(open ? draft : value).toUpperCase()}
      </button>
      <input ref={hidden} type="color" name={name} className="sr-only" tabIndex={-1} disabled={disabled} defaultValue={value} />
      <AnimatePresence>
        {open && (
          <motion.div
            className="gf-color-popover"
            initial={{ opacity: 0, y: -6, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.98, transition: { duration: 0.1 } }}
            transition={{ type: 'spring', stiffness: 460, damping: 32 }}
          >
            <HexColorPicker color={draft} onChange={setDraft} />
            <div className="mt-2.5 flex flex-wrap gap-1.5">
              {SWATCHES.map((swatch) => (
                <button
                  key={swatch}
                  type="button"
                  className="gf-color-swatch"
                  style={{ background: swatch }}
                  aria-label={swatch}
                  onClick={() => setDraft(swatch)}
                />
              ))}
            </div>
            <div className="mt-2.5 flex items-center gap-2">
              <span className="font-mono text-[12px] text-muted">#</span>
              <HexColorInput className="field h-7 min-w-0 flex-1 font-mono text-[12px] uppercase" color={draft} onChange={setDraft} />
              <button type="button" className="btn btn-primary h-7 px-3" onClick={close}>
                OK
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
