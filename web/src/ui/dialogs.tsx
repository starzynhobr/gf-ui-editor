// Diálogos da casca (pergunta, aviso, texto) chamados como funções: `await ask({...})`.
// Equivalem aos QMessageBox/QInputDialog da clássica. Um host desenha a pilha.
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { create } from 'zustand'
import { t, useT } from '../i18n'
import { Icon } from './Icon'

export type Tone = 'info' | 'warning' | 'error' | 'question'

export interface Choice {
  id: string
  label: string
  kind?: 'primary' | 'danger' | 'normal'
}

interface AskSpec {
  type: 'ask'
  title: string
  text: string
  detail?: string
  tone: Tone
  choices: Choice[]
  check?: { label: string; checked: boolean }
  resolve: (value: { choice: string | null; checked: boolean }) => void
}

interface PromptSpec {
  type: 'prompt'
  title: string
  label: string
  value: string
  resolve: (value: string | null) => void
}

interface CustomSpec {
  type: 'custom'
  render: (close: () => void) => ReactNode
}

type Spec = (AskSpec | PromptSpec | CustomSpec) & { id: number }

const useDialogs = create<{ stack: Spec[] }>(() => ({ stack: [] }))
let nextId = 0

function push(spec: AskSpec | PromptSpec | CustomSpec): number {
  nextId += 1
  const id = nextId
  useDialogs.setState((state) => ({ stack: [...state.stack, { ...spec, id }] }))
  return id
}

function remove(id: number): void {
  useDialogs.setState((state) => ({ stack: state.stack.filter((item) => item.id !== id) }))
}

/** Fecha tudo sem responder (testes). */
export function resetDialogs(): void {
  useDialogs.setState({ stack: [] })
}

/** Pergunta com botões (e uma caixa de seleção opcional). `choice` null = fechou/cancelou. */
export function ask(options: Omit<AskSpec, 'type' | 'resolve' | 'tone'> & { tone?: Tone }) {
  return new Promise<{ choice: string | null; checked: boolean }>((resolve) =>
    push({ type: 'ask', tone: 'question', ...options, resolve }),
  )
}

/** Sim/Não. */
export async function confirm(title: string, text: string): Promise<boolean> {
  const { choice } = await ask({
    title,
    text,
    choices: [
      { id: 'no', label: t('Não') },
      { id: 'yes', label: t('Sim'), kind: 'primary' },
    ],
  })
  return choice === 'yes'
}

/** Aviso com um botão OK (information/warning/critical da clássica). */
export async function message(tone: Exclude<Tone, 'question'>, title: string, text: string, detail?: string): Promise<void> {
  await ask({ tone, title, text, detail, choices: [{ id: 'ok', label: t('OK'), kind: 'primary' }] })
}

/** Campo de texto (QInputDialog.getText). null = cancelou. */
export function prompt(title: string, label: string, value = ''): Promise<string | null> {
  return new Promise((resolve) => push({ type: 'prompt', title, label, value, resolve }))
}

/** Diálogo com conteúdo próprio (ex.: Novo projeto). Devolve uma função que o fecha. */
export function openDialog(render: (close: () => void) => ReactNode): () => void {
  let id = 0
  const close = () => remove(id)
  id = push({ type: 'custom', render: () => render(close) })
  return close
}

const TONE_ICON: Record<Tone, [string, string]> = {
  info: ['info', 'text-accent-text'],
  question: ['info', 'text-accent-text'],
  warning: ['alert', 'text-warning'],
  error: ['alert', 'text-danger'],
}

export function Modal({
  title,
  children,
  onClose,
  width = 460,
  footer,
}: {
  title: string
  children: ReactNode
  onClose: () => void
  width?: number
  footer?: ReactNode
}) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation()
        onClose()
      }
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [onClose])
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--color-overlay)] p-4 backdrop-blur-[2px] animate-[fade_120ms_ease-out]">
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="flex max-h-full flex-col rounded-xl border border-border-strong bg-panel shadow-2xl shadow-black/50"
        style={{ width }}
      >
        <div className="flex items-center gap-2 border-b border-border px-5 py-3">
          <div className="flex-1 text-[14px] font-semibold text-bright">{title}</div>
          <button className="icon-button" onClick={onClose} aria-label={t('Fechar')}>
            <Icon name="x" />
          </button>
        </div>
        <div className="min-h-0 overflow-auto px-5 py-4">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t border-border px-5 py-3">{footer}</div>}
      </div>
    </div>
  )
}

function AskDialog({ spec }: { spec: AskSpec & { id: number } }) {
  const [checked, setChecked] = useState(spec.check?.checked ?? false)
  const finish = (choice: string | null) => {
    remove(spec.id)
    spec.resolve({ choice, checked })
  }
  const [icon, color] = TONE_ICON[spec.tone]
  return (
    <Modal
      title={spec.title}
      onClose={() => finish(null)}
      footer={spec.choices.map((choice, index) => (
        <button
          key={choice.id}
          autoFocus={index === spec.choices.length - 1}
          className={choice.kind === 'primary' ? 'btn btn-primary' : choice.kind === 'danger' ? 'btn btn-danger' : 'btn'}
          onClick={() => finish(choice.id)}
        >
          {choice.label}
        </button>
      ))}
    >
      <div className="flex gap-3">
        <Icon name={icon} size={22} className={`mt-0.5 ${color}`} />
        <div className="min-w-0 flex-1 space-y-2">
          <div className="whitespace-pre-wrap text-text">{spec.text}</div>
          {spec.detail && <div className="whitespace-pre-wrap text-muted">{spec.detail}</div>}
          {spec.check && (
            <label className="flex items-center gap-2 pt-1 text-text">
              <input type="checkbox" checked={checked} onChange={(event) => setChecked(event.target.checked)} />
              {spec.check.label}
            </label>
          )}
        </div>
      </div>
    </Modal>
  )
}

function PromptDialog({ spec }: { spec: PromptSpec & { id: number } }) {
  const [value, setValue] = useState(spec.value)
  const input = useRef<HTMLInputElement>(null)
  useEffect(() => input.current?.select(), [])
  const finish = (result: string | null) => {
    remove(spec.id)
    spec.resolve(result)
  }
  return (
    <Modal
      title={spec.title}
      onClose={() => finish(null)}
      footer={
        <>
          <button className="btn" onClick={() => finish(null)}>
            {t('Cancelar')}
          </button>
          <button className="btn btn-primary" onClick={() => finish(value)}>
            {t('OK')}
          </button>
        </>
      }
    >
      <label className="block space-y-1.5">
        <span className="text-muted">{spec.label}</span>
        <input
          ref={input}
          autoFocus
          className="field w-full"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={(event) => event.key === 'Enter' && finish(value)}
        />
      </label>
    </Modal>
  )
}

export function DialogHost() {
  useT()
  const stack = useDialogs((state) => state.stack)
  return (
    <>
      {stack.map((spec) =>
        spec.type === 'ask' ? (
          <AskDialog key={spec.id} spec={spec} />
        ) : spec.type === 'prompt' ? (
          <PromptDialog key={spec.id} spec={spec} />
        ) : (
          <div key={spec.id}>{spec.render(() => remove(spec.id))}</div>
        ),
      )}
    </>
  )
}
