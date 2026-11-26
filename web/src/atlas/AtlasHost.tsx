import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { openTextureFile } from '../shell/textureFile'
import { t as shellT } from '../i18n'
import { createPortal } from 'react-dom'
import { call, type AtlasCuts, type AtlasElement, type CanvasRect } from '../bridge'
import { applyEdits, useDoc, type Edit } from '../doc/store'
import { AtlasResizeCheckbox } from '../canvas/CanvasToolbar'
import { closeAtlas, useAtlasRequest } from './index'
import { AtlasSurface, type Frame } from './AtlasSurface'
import { clamp } from './geometry'
import { atlasStrings } from './strings'
import { useAtlasTexture } from './texture'
import { Icon } from '../ui/Icon'
import { Select } from '../ui/Select'
import './atlas.css'

type Request = NonNullable<ReturnType<typeof useAtlasRequest>>
type State = keyof ReturnType<typeof atlasStrings>['states']
const emptyCuts: AtlasCuts = {}
const normal = 'NorUV'

function thumbnailSize([, , width, height]: CanvasRect): [number, number] {
  const ratio = Math.min(56 / width, 56 / height)
  return [Math.max(1, Math.round(width * ratio)), Math.max(1, Math.round(height * ratio))]
}

function Thumbnail({ bitmap, cut }: { bitmap: ImageBitmap | null | undefined; cut?: CanvasRect }) {
  const canvas = useRef<HTMLCanvasElement>(null)
  const visible = Boolean(cut && cut[2] > 0 && cut[3] > 0)
  const [width, height] = cut && visible ? thumbnailSize(cut) : [1, 1]
  useEffect(() => {
    const context = canvas.current?.getContext('2d')
    if (!context || !bitmap || !cut) return
    context.clearRect(0, 0, width, height)
    context.imageSmoothingEnabled = false
    context.drawImage(bitmap, ...cut, 0, 0, width, height)
  }, [bitmap, cut, width, height])
  return <span className="gf-atlas-thumb gf-atlas-checker" aria-hidden="true">
    {visible && <canvas ref={canvas} width={width} height={height} />}
  </span>
}

function Coordinate({ label, tip, value, min, max, disabled, onChange }: {
  label: string; tip: string; value: number; min: number; max: number; disabled: boolean; onChange: (value: number) => void
}) {
  const [draft, setDraft] = useState<string>()
  return <label title={tip}><span>{label}</span><input type="number" value={draft ?? value} min={min} max={max}
    disabled={disabled} onWheel={(event) => event.currentTarget.blur()}
    onBlur={() => setDraft(undefined)}
    onChange={(event) => {
      const { value: next, valueAsNumber } = event.currentTarget
      setDraft(next)
      if (Number.isFinite(valueAsNumber)) onChange(clamp(Math.trunc(valueAsNumber), min, max))
    }} /></label>
}

function AtlasDialog({ request, language, element }: { request: Request; language: string; element?: AtlasElement }) {
  const t = atlasStrings(language)
  const dialog = useRef<HTMLDialogElement>(null)
  const submitting = useRef(false)
  const [baseline, setBaseline] = useState(() => element?.atlas_uvs ?? emptyCuts)
  const [cuts, setCuts] = useState(baseline)
  const [state, setState] = useState<State>(baseline.ThumbUV ? 'ThumbUV' : normal)
  const [frame, setFrame] = useState<Frame>(() => ({ mode: 'crop', crop: cuts[state] }))
  const [editing, setEditing] = useState(false)
  const [resize, setResize] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [cursor, setCursor] = useState<[number, number] | null>(null)
  const locked = useDoc((doc) => request.kind === 'edit' && doc.locked.includes(request.index))
  const editable = Boolean(element?.texture && cuts[normal])
  const name = request.kind === 'preview' ? request.path.split(/[/\\]/).at(-1)! : element?.texture ?? ''
  const bitmap = useAtlasTexture(request.path, name)
  const cut = cuts[state]
  const enabled = editable && editing && !!bitmap && !locked && !busy
  const buttonStates: State[] = cuts.ThumbUV ? [normal, 'ThumbUV'] : [normal, 'FocusUV', 'DownUV', 'DisableUV']

  useLayoutEffect(() => {
    const node = dialog.current!
    node.showModal()
    return () => node.close()
  }, [])

  function setCrop(next: CanvasRect) {
    setCuts((previous) => ({ ...previous, [state]: next }))
  }

  async function apply() {
    if (request.kind !== 'edit' || !element || !enabled || submitting.current) return
    submitting.current = true
    setBusy(true)
    setError('')
    try {
      const edits = await call<Edit[]>('doc_atlas_plan', request.path, request.index, baseline, cuts, resize)
      const current = useDoc.getState()
      if (current.path !== request.path || current.doc?.elements[request.index]?.texture !== element.texture) {
        throw new Error(t.changed)
      }
      if (current.locked.includes(request.index)) throw new Error(t.locked)
      await applyEdits(edits, `${t.undo} ${element.id}`)
      setBaseline(cuts)
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure))
    } finally {
      submitting.current = false
      setBusy(false)
    }
  }

  const preview = request.kind === 'preview'
  const button = Boolean(element?.button || cuts.ThumbUV)
  const stateLabel = (option: State) => ({
    NorUV: shellT('Normal'), FocusUV: shellT('Mouse sobre (hover)'), DownUV: shellT('Pressionado'),
    DisableUV: shellT('Desativado'), ThumbUV: shellT('Cursor do slider'),
  })[option]
  const heading = state === normal ? shellT('RECORTE NORMAL (NorUV)') : `${stateLabel(state)} (${state})`
  const hint = preview
    ? shellT('Arraste para mover · roda = zoom · a imagem se atualiza ao salvar no editor')
    : enabled
      ? shellT('Arraste para marcar · arraste por dentro para mover · cantos e bordas ajustam · botão do meio navega · roda = zoom')
      : shellT('Arraste para mover a vista · roda = zoom · Editar posição libera o recorte')
  const openDds = () => {
    // Edição: a textura fica ao lado do XML; prévia: o caminho já é o da textura.
    const slash = Math.max(request.path.lastIndexOf('/'), request.path.lastIndexOf(String.fromCharCode(92)))
    const base = request.kind === 'edit' ? request.path : request.path.slice(0, slash + 1) + '_'
    void openTextureFile(base, name)
  }

  // Mesma organização do AtlasDialog da clássica: textura à esquerda e, na lateral, nome e
  // tamanho, Centralizar | Atlas inteiro, Editar posição, estado do botão, recorte, Abrir .dds,
  // dica, cursor e, no rodapé, Fechar e Aplicar.
  return (
    <dialog ref={dialog} role="dialog" className="gf-atlas-dialog" aria-labelledby="gf-atlas-title"
      onCancel={(event) => { event.preventDefault(); if (!busy) closeAtlas() }}>
      <div className="gf-atlas-layout">
        <AtlasSurface bitmap={bitmap} label={!name ? t.unavailable : bitmap === null ? t.error : t.loading}
          cut={preview ? undefined : cut} editing={enabled} frame={frame} onCrop={setCrop}
          onCursor={(point) => { if (point) setCursor(point) }} />
        <aside className="gf-atlas-side" data-testid="atlas-side">
          <div className="gf-atlas-heading">
            <h2 id="gf-atlas-title" title={preview ? shellT('Textura — {name}', { name }) : shellT('Atlas DDS — {name}', { name })}>
              {name || t.title}
            </h2>
            <p data-testid="atlas-size">
              {bitmap ? `${bitmap.width} × ${bitmap.height} px` : bitmap === null ? shellT('Não foi possível ler a imagem.') : ' '}
            </p>
          </div>
          <div className={preview ? 'gf-atlas-row gf-atlas-row-single' : 'gf-atlas-row'}>
            {!preview && (
              <button type="button" className="btn" disabled={!bitmap || !cut}
                title={shellT('Aproxima e enquadra o recorte NorUV selecionado atualmente.')}
                onClick={() => setFrame({ mode: 'crop', crop: cut })}>
                <Icon name="focus" size={16} />{shellT('Centralizar')}
              </button>
            )}
            <button type="button" className="btn" disabled={!bitmap} onClick={() => setFrame({ mode: 'fit' })}>
              <Icon name="frame" size={16} />{shellT('Atlas inteiro')}
            </button>
          </div>
          {!preview && (
            <button type="button" className="btn btn-primary gf-atlas-edit" aria-pressed={editing} data-testid="atlas-edit"
              disabled={!editable || !bitmap || locked || busy}
              title={shellT('Libera o recorte para ser marcado ou ajustado. Sem isto, arrastar só move a vista.')}
              onClick={() => setEditing(!editing)}>
              <Icon name="frame" size={16} />{editing ? shellT('Editando posição') : shellT('Editar posição')}
            </button>
          )}
          {!preview && editable && button && (
            <section className="gf-atlas-card" data-testid="atlas-state-card">
              <span className="gf-atlas-card-title">{shellT('Estado do botão')}</span>
              <Select size="sm" label={shellT('Estado do botão')} value={state} testId="atlas-state" disabled={busy}
                options={(cuts.ThumbUV ? [normal, 'ThumbUV'] as State[] : buttonStates).map((option) => ({
                  value: option,
                  label: cuts[option] ? stateLabel(option) : shellT('{state} — não definido', { state: stateLabel(option) }),
                  disabled: !cuts[option],
                }))}
                onChange={(value) => {
                  const next = value as State
                  setState(next)
                  setFrame({ mode: 'crop', crop: cuts[next] })
                }} />
              <Thumbnail bitmap={bitmap} cut={cut} />
            </section>
          )}
          {!preview && editable && cut && (
            <section className="gf-atlas-card" data-testid="atlas-uv-card">
              <span className="gf-atlas-card-title gf-atlas-legend">{heading}</span>
              <div className="gf-atlas-fields">
                {['X', 'Y', shellT('L   ').trim(), shellT('A   ').trim()].map((label, index) => (
                  <Coordinate key={`${state}:${index}`} label={label} value={cut[index]}
                    tip={state + ['Left', 'Top', 'Width', 'Height'][index]}
                    min={index < 2 ? -100000 : (button ? 0 : 1)}
                    max={(index % 2 === 0 ? bitmap?.width ?? 1 : bitmap?.height ?? 1) - (index < 2 ? 1 : 0)}
                    disabled={!enabled} onChange={(value) => {
                      const next: CanvasRect = [...cut]
                      next[index] = value
                      setCrop(next)
                    }} />
                ))}
              </div>
              <AtlasResizeCheckbox label={shellT('Elemento com o tamanho do recorte')} checked={resize}
                disabled={!enabled || state !== normal} onChange={setResize} />
            </section>
          )}
          <button type="button" className="btn gf-atlas-open-dds" data-testid="atlas-open-dds" disabled={!name}
            title={preview
              ? shellT('Abre no programa padrão do Windows para .dds (Paint.NET, por exemplo)')
              : shellT('Abre esta textura no aplicativo padrão do sistema.')}
            onClick={openDds}>
            <Icon name="image" size={16} />{shellT('Abrir .dds')}
          </button>
          <div className="gf-atlas-spacer" />
          {!preview && !editable && name && <p role="status">{t.unavailable}</p>}
          {locked && <p role="status">{t.locked}</p>}
          {error && <p role="alert">{error}</p>}
          <p className="gf-atlas-hint">{hint}</p>
          <p className="gf-atlas-cursor" data-testid="atlas-cursor">
            {cursor ? shellT('Cursor: X {x} · Y {y}', { x: cursor[0], y: cursor[1] }) : shellT('Cursor: —')}
          </p>
          <footer className="gf-atlas-footer">
            <button type="button" className="btn gf-atlas-close" disabled={busy} onClick={closeAtlas}>{shellT('Fechar')}</button>
            {!preview && (
              <button type="button" className="btn btn-primary gf-atlas-apply" disabled={!enabled} onClick={() => void apply()}>
                {shellT('Aplicar')}
              </button>
            )}
          </footer>
        </aside>
      </div>
    </dialog>
  )
}

export function AtlasHost({ language }: { language: string }) {
  const request = useAtlasRequest()
  const docPath = useDoc((doc) => doc.path)
  const element = useDoc((doc) => request?.kind === 'edit' ? doc.doc?.elements[request.index] as AtlasElement | undefined : undefined)
  useEffect(() => {
    if (request?.kind === 'edit' && request.path !== docPath) closeAtlas()
  }, [request, docPath])
  if (!request || (request.kind === 'edit' && request.path !== docPath)) return null
  const key = request.kind === 'edit' ? `${request.index}:${request.path}:${element?.texture}` : request.path
  return createPortal(<AtlasDialog key={key} request={request} language={language} element={element} />, document.body)
}
