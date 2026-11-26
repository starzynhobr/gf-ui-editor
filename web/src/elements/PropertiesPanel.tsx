// Painel de propriedades (direita), como o PropertyPanel da clássica: posição e tamanho,
// textura, identificação e aparência/fonte (só os campos que o controle tem no XML).
// Toda edição vai por applyEdits (um passo de desfazer).
import { ColorPicker } from '../ui/ColorPicker'
import { Select } from '../ui/Select'
import { atlasModule } from '../shell/atlas'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { api, type TreeRow } from '../api'
import type { CanvasElement, CanvasRect } from '../bridge'
import { useT } from '../i18n'
import { useShell } from '../store'
import { editElement, changeTexture } from './edits'
import { useDocState, useEditingAvailable } from '../shell/doc'
import { Icon } from '../ui/Icon'
import { FONT_FIELDS, gameColorToHex, hexToGameColor, kindLabel } from './kinds'

/** Campo numérico: setas ±1 (Shift ±10), Enter/sair do campo grava, roda do mouse não muda. */
function NumberField({
  prefix,
  value,
  min = -100000,
  max = 100000,
  disabled,
  title,
  name,
  onCommit,
}: {
  prefix: string
  value: number
  min?: number
  max?: number
  disabled?: boolean
  title?: string
  name?: string
  onCommit: (value: number) => Promise<boolean> | void
}) {
  const [text, setText] = useState(String(value))
  const editing = useRef(false)
  useEffect(() => {
    if (!editing.current) setText(String(value))
  }, [value])
  const clamp = (number: number) => Math.max(min, Math.min(max, Math.round(number)))
  const commit = (raw: string) => {
    editing.current = false
    const number = Number.parseInt(raw, 10)
    if (!Number.isFinite(number)) {
      setText(String(value))
      return
    }
    const next = clamp(number)
    setText(String(next))
    if (next !== value) send(next)
  }
  // Edição recusada (travado, store indisponível, erro): o campo volta ao valor do documento.
  const send = (next: number) =>
    void Promise.resolve(onCommit(next)).then((ok) => {
      if (ok === false) setText(String(value))
    })
  return (
    <label
      className={`field flex items-center gap-2 font-mono text-[12px] ${disabled ? 'opacity-50' : ''}`}
      title={title}
      onWheel={(event) => event.currentTarget.querySelector('input')?.blur()}
    >
      <span className="w-3 text-muted">{prefix}</span>
      <input
        name={name}
        className="min-w-0 flex-1 bg-transparent outline-none"
        inputMode="numeric"
        disabled={disabled}
        value={text}
        onFocus={(event) => event.target.select()}
        onChange={(event) => {
          editing.current = true
          setText(event.target.value.replace(/[^\d-]/g, ''))
        }}
        onBlur={(event) => commit(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter') {
            commit(event.currentTarget.value)
            event.currentTarget.blur()
          } else if (event.key === 'Escape') {
            editing.current = false
            setText(String(value))
            event.currentTarget.blur()
          } else if (event.key === 'ArrowUp' || event.key === 'ArrowDown') {
            event.preventDefault()
            const base = Number.parseInt(event.currentTarget.value, 10)
            const step = (event.shiftKey ? 10 : 1) * (event.key === 'ArrowUp' ? 1 : -1)
            const next = clamp((Number.isFinite(base) ? base : value) + step)
            setText(String(next))
            editing.current = false
            send(next)
          }
        }}
      />
    </label>
  )
}

function Card({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="card space-y-2.5 px-3 py-3">
      <div className="section-label">{title}</div>
      {children}
    </section>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[96px_minmax(0,1fr)] items-center gap-2">
      <span className="text-[12px] text-muted">{label}</span>
      <div className="min-w-0">{children}</div>
    </div>
  )
}

function Choice({
  value,
  options,
  disabled,
  title,
  onChange,
}: {
  value: string
  options: [string, string][]
  disabled?: boolean
  title?: string
  onChange: (value: string) => void
}) {
  // Valor fora do comum aparece como está (como a clássica).
  const all = options.some(([data]) => data === value) ? options : [...options, [value, value] as [string, string]]
  return (
    <Select
      size="sm"
      className="w-full"
      value={value}
      disabled={disabled}
      title={title}
      options={all.map(([data, label]) => ({ value: data, label }))}
      onChange={onChange}
    />
  )
}

export default function PropertiesPanel() {
  const t = useT()
  const path = useDocState((state) => state.path)
  const doc = useDocState((state) => state.doc)
  const selection = useDocState((state) => state.selection)
  const locked = useDocState((state) => state.locked)
  const editable = useEditingAvailable()
  const revision = useShell((state) => state.revision)
  const [row, setRow] = useState<TreeRow | null>(null)
  const primary = selection[0] ?? null
  const element: CanvasElement | null = doc && primary != null ? (doc.elements[primary] ?? null) : null

  useEffect(() => {
    let alive = true
    setRow(null)
    if (path && doc && element) {
      void api
        .elementTree(path, doc.elements.map((item) => item.kind))
        .then((rows) => alive && setRow(rows.find((item) => item.index === element.index) ?? null))
        .catch(() => undefined)
    }
    return () => {
      alive = false
    }
  }, [path, doc, element?.index, revision]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!element || !doc) {
    return (
      <div className="space-y-1.5 p-4" data-testid="properties-panel">
        <div className="text-[14px] font-semibold text-bright">{t('Nenhum elemento selecionado')}</div>
        <div className="text-[12.5px] leading-snug text-muted">{t('Selecione um item no canvas ou na lista para editar sua geometria.')}</div>
      </div>
    )
  }

  const isLocked = locked.includes(element.index)
  const disabled = isLocked || !editable
  const kind = kindLabel(element.kind, element.ctrl_type)
  const font = fontFields(element)
  const geometry = element.geometry
  const setGeometry = (position: number, value: number) => {
    const after = [...geometry] as CanvasRect
    after[position] = value
    return editElement(
      [{ index: element.index, field: 'geometry', before: geometry, after }],
      t('Mover/redimensionar WindowID {id}', { id: element.id }),
    )
  }
  const setFont = (name: string, value: string) => {
    const before = font[name]
    if (before === undefined || before === value) return Promise.resolve(true)
    return editElement([{ index: element.index, field: 'font', name, before, after: value }], `${name} = ${value}`)
  }
  const title = row?.text || `WindowID ${element.id}`
  const uv = element.uv

  return (
    <div className="space-y-3 p-4" data-testid="properties-panel">
      <div className="space-y-1">
        <div className="flex items-center gap-2">
          <span className="rounded-full bg-accent-soft px-2 py-px text-[11px] text-accent-text">{kind}</span>
          <span className="font-mono text-[11px] text-muted">
            {element.parent ? t('dentro de {parent}', { parent: element.parent }) : t('raiz')}
          </span>
        </div>
        <div className="selectable truncate text-[15px] font-semibold text-bright" title={title} data-testid="properties-title">
          {title}
          {selection.length > 1 && <span className="font-normal text-muted">{t(' · {count} selecionados', { count: selection.length })}</span>}
        </div>
        {isLocked && <div className="text-[12px] text-accent-text">{t('Bloqueado')}</div>}
      </div>

      <Card title={t('POSIÇÃO E TAMANHO')}>
        <div className="grid grid-cols-2 gap-2">
          <NumberField name="geometry-x" prefix="X" value={geometry[0]} disabled={disabled} title={t('WindowLeft no XML')} onCommit={(value) => setGeometry(0, value)} />
          <NumberField name="geometry-y" prefix="Y" value={geometry[1]} disabled={disabled} title={t('WindowTop no XML')} onCommit={(value) => setGeometry(1, value)} />
          <NumberField name="geometry-w" prefix={t('L   ').trim()} min={0} value={geometry[2]} disabled={disabled} title={t('WindowHeight no XML')} onCommit={(value) => setGeometry(2, value)} />
          <NumberField name="geometry-h" prefix={t('A   ').trim()} min={0} value={geometry[3]} disabled={disabled} title={t('WindowWidth no XML')} onCommit={(value) => setGeometry(3, value)} />
        </div>
      </Card>

      <Card title={t('TEXTURA')}>
        <Field label={t('Arquivo')}>
          <input readOnly className="field h-7 w-full font-mono text-[12px]" value={element.texture ?? ''} data-testid="texture-name" />
        </Field>
        <Field label={t('Recorte DDS')}>
          <span className="font-mono text-[12px] text-text">{uv ? `X ${uv[0]} · Y ${uv[1]} · ${uv[2]} × ${uv[3]}` : '—'}</span>
        </Field>
        <button
          className="btn h-7 w-full"
          disabled={disabled || element.texture == null}
          title={t('Usa outro .dds neste controle: um da UI, uma cópia para editar ou um de outra pasta')}
          onClick={(event) => void changeTexture(event.currentTarget, element)}
        >
          <Icon name="image" size={15} />
          {t('Trocar .dds…')}
        </button>
        <button
          className="btn mt-1.5 h-7 w-full"
          disabled={element.texture == null}
          data-testid="open-atlas"
          onClick={() => void atlasModule().then((atlas) => atlas?.openAtlas(element.index))}
        >
          <Icon name="layout" size={15} />
          {t('Abrir atlas DDS…')}
        </button>
      </Card>

      <Card title={t('IDENTIFICAÇÃO')}>
        <Field label="WindowID">
          <span className="selectable font-mono text-[12px] text-text">{element.id}</span>
        </Field>
        <Field label={t('Tipo')}>
          <span className="text-text">{kind}</span>
        </Field>
        <Field label="ParentNode">
          <span className="font-mono text-[12px] text-text">{element.parent ?? '—'}</span>
        </Field>
        <Field label="CtrlType">
          <span className="font-mono text-[12px] text-text">{element.ctrl_type ?? '—'}</span>
        </Field>
      </Card>

      <Card title={t('APARÊNCIA')}>
        <Field label={t('Visível no XML')}>
          <input type="checkbox" checked={element.visible} disabled readOnly />
        </Field>
        <Field label={t('Texto')}>
          <span
            className={`selectable block truncate text-[12.5px] ${row?.text ? 'text-text' : 'text-disabled'}`}
            title={t('WindowText do XML (só leitura). Nos controles de texto o jogo pode trocar pelo texto do T_TextIndex; edite pela tela Textos ou com duplo clique no elemento.')}
          >
            {row?.text || '—'}
          </span>
        </Field>
        {Object.keys(font).length === 0 && (
          <Field label={t('Fonte')}>
            <span className="text-muted">{t('Sem texto próprio')}</span>
          </Field>
        )}
        {font.FontColor !== undefined && (
          <Field label={t('Cor do texto')}>
            <ColorPicker
              name="font-color"
              disabled={disabled}
              title={t('FontColor no XML. Clique para escolher a cor.')}
              value={gameColorToHex(font.FontColor)}
              onCommit={(hex) => setFont('FontColor', hexToGameColor(hex))}
              swatchesLabel={t('Cores usadas pelo jogo')}
            />
          </Field>
        )}
        {font.FontStyle !== undefined && (
          <Field label={t('Contorno')}>
            <Choice
              value={font.FontStyle}
              disabled={disabled}
              title={t('FontStyle no XML: o jogo desenha um contorno preto em volta das letras.')}
              options={[['0', t('Sem contorno')], ['1', t('Com contorno')]]}
              onChange={(value) => setFont('FontStyle', value)}
            />
          </Field>
        )}
        {font.TextAlign !== undefined && (
          <Field label={t('Alinhamento')}>
            <Choice
              value={font.TextAlign}
              disabled={disabled}
              title={element.kind === 'button' ? t('TextAlign no XML. Em botões o jogo centraliza o texto sempre.') : t('TextAlign no XML.')}
              options={[['0', t('Esquerda')], ['1', t('Centro')], ['2', t('Direita')]]}
              onChange={(value) => setFont('TextAlign', value)}
            />
          </Field>
        )}
        {font.FontSize !== undefined && (
          <Field label={t('Tamanho')}>
            <NumberField
              prefix=""
              min={1}
              max={72}
              value={Number.parseInt(font.FontSize, 10) || 9}
              disabled={disabled}
              title={t('FontSize no XML. O preview desenha sempre com a fonte do cliente (Arial 8); o tamanho só aparece no jogo.')}
              onCommit={(value) => setFont('FontSize', String(value))}
            />
          </Field>
        )}
        <p className="text-[11.5px] leading-snug text-muted">
          {t('O formato do jogo usa WindowHeight como largura visual e WindowWidth como altura visual.')}
        </p>
      </Card>
    </div>
  )
}

/** Campos de fonte que o controle tem no XML (o canvas manda font_attrs; senão, pelos text_props). */
export function fontFields(element: CanvasElement): Record<string, string> {
  const explicit = (element as CanvasElement & { font_attrs?: Record<string, string> }).font_attrs
  if (explicit) return explicit
  return Object.fromEntries(FONT_FIELDS.filter((name) => name in element.text_props).map((name) => [name, element.text_props[name]]))
}
