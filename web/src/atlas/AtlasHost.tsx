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
import './atlas.css'

type Request = NonNullable<ReturnType<typeof useAtlasRequest>>
type State = keyof ReturnType<typeof atlasStrings>['states']
const emptyCuts: AtlasCuts = {}
const normal = 'NorUV'

function thumbnailSize([, , width, height]: CanvasRect): [number, number] {
  const ratio = Math.min(52 / width, 42 / height)
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

function Coordinate({ label, value, min, max, disabled, onChange }: {
  label: string; value: number; min: number; max: number; disabled: boolean; onChange: (value: number) => void
}) {
  const [draft, setDraft] = useState<string>()
  return <label>{label}<input type="number" value={draft ?? value} min={min} max={max}
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

  return (
    <dialog ref={dialog} role="dialog" className="gf-atlas-dialog" aria-labelledby="gf-atlas-title"
      onCancel={(event) => { event.preventDefault(); if (!busy) closeAtlas() }}>
      <header>
        <h2 id="gf-atlas-title">{t.title}{name && <> <span>{name}</span></>}</h2>
        {bitmap && <span>{bitmap.width} × {bitmap.height} px</span>}
        {name && (
          <button type="button" className="gf-atlas-open-dds" data-testid="atlas-open-dds"
            onClick={() => {
              // Edição: a textura fica ao lado do XML; prévia: o caminho já é o da textura.
              const cut = Math.max(request.path.lastIndexOf('/'), request.path.lastIndexOf(String.fromCharCode(92)))
              const base = request.kind === 'edit' ? request.path : request.path.slice(0, cut + 1) + '_'
              void openTextureFile(base, name)
            }}>{shellT('Abrir .dds')}</button>
        )}
        <button type="button" className="gf-atlas-close" aria-label={t.close} disabled={busy} onClick={closeAtlas}>×</button>
      </header>
      <div className="gf-atlas-layout">
        <div className="gf-atlas-view">
          <div className="gf-atlas-tools">
            <button type="button" disabled={!bitmap} onClick={() => setFrame({ mode: 'fit' })}>{t.fit}</button>
            {cut && <button type="button" disabled={!bitmap} onClick={() => setFrame({ mode: 'crop', crop: cut })}>{t.center}</button>}
            <button type="button" aria-label={t.zoomOut} disabled={!bitmap} onClick={() => setFrame({ mode: 'zoom', factor: 1 / 1.2 })}>−</button>
            <button type="button" aria-label={t.zoomIn} disabled={!bitmap} onClick={() => setFrame({ mode: 'zoom', factor: 1.2 })}>+</button>
          </div>
          <AtlasSurface bitmap={bitmap} label={!name ? t.unavailable : bitmap === null ? t.error : t.loading}
            cut={cut} editing={enabled} frame={frame} onCrop={setCrop} />
          <p className="gf-atlas-hint">{enabled ? t.drag : t.pan}</p>
        </div>
        {editable && <aside className="gf-atlas-controls">
          <button type="button" aria-pressed={editing} disabled={!bitmap || locked || busy}
            onClick={() => setEditing(!editing)}>{t.edit}</button>
          <div className="gf-atlas-states">
            {(element?.button || cuts.ThumbUV ? buttonStates : [normal] as State[]).map((name) =>
              <button key={name} type="button" data-state={name} aria-pressed={state === name} disabled={!cuts[name] || busy} onClick={() => {
                setState(name)
                setFrame({ mode: 'crop', crop: cuts[name] })
              }}>
                <Thumbnail bitmap={bitmap} cut={cuts[name]} />{t.states[name]}
              </button>,
            )}
          </div>
          {cut && <fieldset className="gf-atlas-fields">
            <legend>{t.crop} ({state})</legend>
            {['X', 'Y', t.width, t.height].map((label, index) => (
              <Coordinate key={`${state}:${index}`} label={label} value={cut[index]}
                min={index < 2 ? -100000 : (element?.button || cuts.ThumbUV ? 0 : 1)}
                max={(index % 2 === 0 ? bitmap?.width ?? 1 : bitmap?.height ?? 1) - (index < 2 ? 1 : 0)}
                disabled={!enabled} onChange={(value) => {
                  const next: CanvasRect = [...cut]
                  next[index] = value
                  setCrop(next)
                }} />
            ))}
          </fieldset>}
          <AtlasResizeCheckbox label={t.resize} checked={resize} disabled={!enabled || state !== normal} onChange={setResize} />
          {locked && <p role="status">{t.locked}</p>}
          {error && <p role="alert">{error}</p>}
          <button className="gf-atlas-apply" type="button" disabled={!enabled} onClick={() => void apply()}>{t.apply}</button>
        </aside>}
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
