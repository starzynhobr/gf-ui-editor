// "Exportar para várias resoluções…" (menu Exportar da barra superior). Sem perguntas técnicas:
// o editor decide onde cada janela fica em cada resolução, mostra as prévias lado a lado e a
// pessoa só confere e, se algo ficou fora do lugar, abre a resolução e arrasta. Gera um zip
// por resolução (`<Projeto> 1920x1080.zip`) e, se quiser, o "All Resolution".
import { useCallback, useEffect, useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { api, errorText } from '../api'
import { withProgress } from '../actions'
import { t, useT } from '../i18n'
import { TextureCache } from '../canvas/dds/cache'
import { saveBeforeProjectAction } from '../shell/saving'
import { showStatus } from '../store'
import { ask, message, Modal, openDialog, prompt } from '../ui/dialogs'
import { Icon } from '../ui/Icon'
import { useListAnimation } from '../ui/animate'
import { ResolutionPreview } from './ResolutionPreview'
import { ruleText } from './rules'
import {
  parseSize, resolutionsApi, sameSize, sizeKey, sizeLabel,
  type Info, type PieceInfo, type Plan, type SceneLayer, type Size, type TargetPlan,
} from './resolutionsApi'

const movers = (target: TargetPlan) => target.windows.filter((window) => window.moves)
const adjustedCount = (target: TargetPlan) =>
  target.windows.reduce((sum, window) => sum + window.pieces.filter((piece) => piece.adjusted).length, 0)

function Chip({ on, children, onClick, testId }: { on: boolean; children: React.ReactNode; onClick: () => void; testId?: string }) {
  return (
    <button
      type="button"
      aria-pressed={on}
      data-testid={testId}
      onClick={onClick}
      className={`inline-flex h-8 items-center gap-1.5 rounded-full border px-3 text-[12.5px] transition-colors ${
        on ? 'border-accent-border/70 bg-accent-soft text-accent-text' : 'border-border-input bg-input text-muted hover:border-border-strong hover:text-text'
      }`}
    >
      <Icon name={on ? 'check' : 'x'} size={13} className={on ? '' : 'opacity-0'} />
      {children}
    </button>
  )
}

function TargetCard({ target, layers, cache, onOpen }: {
  target: TargetPlan; layers: SceneLayer[] | undefined; cache: TextureCache | null; onOpen: () => void
}) {
  const moving = movers(target).length
  const adjusted = adjustedCount(target)
  return (
    <motion.button
      layout
      type="button"
      data-testid={`resolution-card-${target.key}`}
      onClick={onOpen}
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.97 }}
      transition={{ duration: 0.18, ease: 'easeOut' }}
      className="group card flex flex-col gap-2 p-2.5 text-left transition-colors hover:border-accent-border/60"
      title={t('Clique para ampliar e arrastar o que ficou fora do lugar')}
    >
      <div className="relative overflow-hidden rounded-md bg-input">
        {layers ? (
          <ResolutionPreview size={target.size} layers={layers} windows={target.windows} cache={cache} />
        ) : (
          <div className="animate-pulse bg-hover" style={{ aspectRatio: `${target.size[0]} / ${target.size[1]}` }} />
        )}
        <span className="pointer-events-none absolute right-2 top-2 rounded-md bg-black/55 px-1.5 py-0.5 text-[11px] text-white opacity-0 transition-opacity group-hover:opacity-100">
          <Icon name="search" size={12} className="mr-1 inline" />
          {t('Ampliar')}
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="font-mono text-[13px] font-semibold text-bright">{sizeLabel(target.size)}</span>
        <div className="flex-1" />
        {moving ? (
          <span className="chip">{t('{count} janela(s) mudam de lugar', { count: moving })}</span>
        ) : (
          <span className="chip">{t('igual à sua tela')}</span>
        )}
        {adjusted > 0 && (
          <span className="chip border-gold/50 text-gold" data-testid="adjusted-chip">
            {t('você ajustou {count}', { count: adjusted })}
          </span>
        )}
        {target.variants.length > 0 && <span className="chip">{t('{count} arquivo(s) só desta', { count: target.variants.length })}</span>}
      </div>
    </motion.button>
  )
}

function FocusView({ target, layers, cache, onBack, onAdjust, onUndo, onUndoAll, onVariants }: {
  target: TargetPlan
  layers: SceneLayer[] | undefined
  cache: TextureCache | null
  onBack: () => void
  onAdjust: (file: string, piece: PieceInfo, point: [number, number]) => void
  onUndo: (file: string, piece: PieceInfo) => void
  onUndoAll: () => void
  onVariants: (action: 'add' | { remove: string }) => void
}) {
  const animate = useListAnimation()
  const [highlight, setHighlight] = useState<string | null>(null)
  const list = movers(target)
  const adjusted = adjustedCount(target)
  return (
    <motion.div
      key="focus"
      data-testid={`resolution-focus-${target.key}`}
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.98 }}
      transition={{ duration: 0.18, ease: 'easeOut' }}
      className="flex min-h-0 gap-4"
    >
      <div className="min-w-0 flex-1 space-y-2">
        <div className="flex items-center gap-2">
          <button className="btn btn-ghost h-7 px-2" onClick={onBack} data-testid="resolution-back">
            <Icon name="chevron-right" size={14} className="rotate-180" />
            {t('Todas as resoluções')}
          </button>
          <span className="font-mono text-[13px] font-semibold text-bright">{sizeLabel(target.size)}</span>
        </div>
        <div className="overflow-hidden rounded-lg border border-border bg-input">
          {layers ? (
            <ResolutionPreview
              size={target.size}
              layers={layers}
              windows={target.windows}
              cache={cache}
              interactive
              highlight={highlight}
              adjustedLabel={t('você ajustou')}
              onAdjust={onAdjust}
            />
          ) : (
            <div className="animate-pulse bg-hover" style={{ aspectRatio: `${target.size[0]} / ${target.size[1]}` }} />
          )}
        </div>
        <p className="text-[12px] text-muted">
          {t('Arraste uma janela para corrigir o lugar dela só nesta resolução. As outras resoluções não mudam.')}
        </p>
      </div>
      <aside className="flex w-[250px] shrink-0 flex-col gap-3">
        <div className="section-label">{t('O que muda de lugar')}</div>
        <div ref={animate} className="max-h-[300px] space-y-1 overflow-y-auto" data-testid="resolution-windows">
          {list.length === 0 && <div className="text-[12px] text-muted">{t('Nada: tudo fica onde o jogo põe.')}</div>}
          {list.map((window) =>
            window.pieces
              .filter((piece) => piece.moved || piece.adjusted)
              .map((piece, index, pieces) => (
                <div
                  key={`${window.file}|${piece.key}`}
                  className="group rounded-md border border-transparent px-2 py-1.5 hover:border-border hover:bg-hover"
                  onMouseEnter={() => setHighlight(window.file)}
                  onMouseLeave={() => setHighlight(null)}
                  data-testid="resolution-window"
                >
                  <div className="flex items-center gap-1.5">
                    <span className="truncate font-mono text-[12px] text-bright" title={window.file}>
                      {window.file}
                      {pieces.length > 1 ? ` · ${index + 1}` : ''}
                    </span>
                    <div className="flex-1" />
                    {piece.adjusted && (
                      <button
                        className="icon-button h-6 w-6"
                        title={t('Desfazer o ajuste (volta para a regra do editor)')}
                        aria-label={t('Desfazer o ajuste')}
                        onClick={() => onUndo(window.file, piece)}
                      >
                        <Icon name="undo" size={14} />
                      </button>
                    )}
                  </div>
                  <div className={`text-[12px] ${piece.adjusted ? 'text-gold' : 'text-muted'}`}>{ruleText(piece, window.kind)}</div>
                </div>
              )),
          )}
        </div>
        {adjusted > 0 && (
          <button className="btn h-7 self-start text-[12px]" onClick={onUndoAll}>
            <Icon name="undo" size={13} />
            {t('Desfazer os ajustes desta resolução')}
          </button>
        )}
        <div className="section-label pt-1">{t('Arquivos só desta resolução')}</div>
        <div className="space-y-1" data-testid="resolution-variants">
          {target.variants.map((name) => (
            <div key={name} className="flex items-center gap-1.5 rounded-md bg-input px-2 py-1">
              <Icon name="image" size={13} className="text-muted" />
              <span className="truncate font-mono text-[12px]">{name}</span>
              <div className="flex-1" />
              <button className="icon-button h-6 w-6" aria-label={t('Tirar')} title={t('Tirar')} onClick={() => onVariants({ remove: name })}>
                <Icon name="x" size={13} />
              </button>
            </div>
          ))}
          <button className="btn h-7 text-[12px]" onClick={() => onVariants('add')}>
            <Icon name="file-import" size={13} />
            {t('Usar outro arquivo nesta resolução…')}
          </button>
          <p className="text-[11.5px] leading-snug text-muted">
            {t('Por exemplo, um main.dds desenhado para esta tela. Ele substitui o do projeto só neste zip.')}
          </p>
        </div>
      </aside>
    </motion.div>
  )
}

function ResolutionsDialog({ onClose }: { onClose: () => void }) {
  useT()
  const [info, setInfo] = useState<Info | null>(null)
  const [base, setBase] = useState<Size | null>(null)
  const [options, setOptions] = useState<Size[]>([])
  const [checked, setChecked] = useState<Size[]>([])
  const [plan, setPlan] = useState<Plan | null>(null)
  const [layers, setLayers] = useState<Record<string, SceneLayer[]>>({})
  const [focus, setFocus] = useState<string | null>(null)
  const [whole, setWhole] = useState(true)
  const [allResolution, setAllResolution] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const cache = useMemo(() => {
    try {
      return new TextureCache()
    } catch {
      return null
    }
  }, [])
  useEffect(() => () => cache?.dispose(), [cache])

  useEffect(() => {
    resolutionsApi.info().then((data) => {
      setInfo(data)
      setBase(data.base)
      const all: Size[] = []
      for (const size of [...data.common, ...data.targets]) if (!all.some((item) => sameSize(item, size))) all.push(size)
      setOptions(all)
      setChecked(data.targets)
    }).catch((reason) => setError(errorText(reason)))
  }, [])

  const ordered = useMemo(
    () => options.filter((size) => checked.some((item) => sameSize(item, size))),
    [options, checked],
  )

  const loadScenes = useCallback(async (baseSize: Size, targets: TargetPlan[]) => {
    for (const target of targets) {
      const files = target.windows.map((window) => window.file)
      try {
        const scenes = await resolutionsApi.scenes(baseSize, target.size, files)
        setLayers((current) => ({ ...current, [`${sizeKey(baseSize)}|${target.key}`]: scenes }))
      } catch (reason) {
        setError(errorText(reason))
      }
    }
  }, [])

  const refresh = useCallback(async (baseSize: Size, targets: Size[], only?: string) => {
    if (!targets.length) {
      setPlan(null)
      return
    }
    try {
      const next = await resolutionsApi.plan(baseSize, targets)
      setPlan(next)
      await loadScenes(baseSize, next.targets.filter((target) => !only || target.key === only))
    } catch (reason) {
      setError(errorText(reason))
    }
  }, [loadScenes])

  useEffect(() => {
    if (!base) return
    void refresh(base, ordered)
    void resolutionsApi.setChoice(base, ordered).catch(() => undefined)
  }, [base, ordered, refresh])

  const toggle = (size: Size) =>
    setChecked((current) => current.some((item) => sameSize(item, size)) ? current.filter((item) => !sameSize(item, size)) : [...current, size])

  const addCustom = async () => {
    const text = await prompt(t('Outra resolução'), t('Largura x altura, por exemplo 1680x1050'), '1680x1050')
    if (text === null) return
    const size = parseSize(text)
    if (!size) {
      await message('warning', t('Outra resolução'), t('Não entendi "{text}". Escreva largura x altura, por exemplo 1680x1050.', { text }))
      return
    }
    setOptions((current) => current.some((item) => sameSize(item, size)) ? current : [...current, size])
    setChecked((current) => current.some((item) => sameSize(item, size)) ? current : [...current, size])
  }

  const focused = plan?.targets.find((target) => target.key === focus) ?? null
  const afterChange = (target: TargetPlan) => base && refresh(base, ordered, target.key)

  const adjust = async (file: string, piece: PieceInfo, point: [number, number] | null) => {
    if (!focused) return
    try {
      await resolutionsApi.adjust(file, piece.key, focused.size, point)
      await afterChange(focused)
    } catch (reason) {
      setError(errorText(reason))
    }
  }

  const variants = async (action: 'add' | { remove: string }) => {
    if (!focused) return
    try {
      if (action === 'add') await resolutionsApi.addVariant(focused.size)
      else await resolutionsApi.removeVariant(focused.size, action.remove)
      await afterChange(focused)
    } catch (reason) {
      await message('error', t('Arquivos só desta resolução'), errorText(reason))
    }
  }

  const zipCount = ordered.length + (allResolution ? 1 : 0)
  const runExport = async () => {
    if (!base || !info || !ordered.length) return
    const folder = await resolutionsApi.pickFolder()
    if (!folder) return
    let result
    try {
      result = await withProgress(t('Gerando os zips…'), () => resolutionsApi.export(folder, base, ordered, whole, allResolution))
    } catch (reason) {
      await message('error', t('Falha ao exportar'), errorText(reason))
      return
    }
    onClose()
    const made = result.zips.filter((zip) => zip.count > 0)
    const same = result.zips.filter((zip) => zip.count === 0).map((zip) => zip.key.replace('x', ' × '))
    const names = made.map((zip) => zip.path.split(/[\\/]/).pop()).join('\n')
    let text = t('{count} zip(s) em {folder}:', { count: made.length, folder }) + '\n\n' + names
    if (same.length) text += '\n\n' + t('Iguais à sua UI, sem zip: {list}.', { list: same.join(', ') })
    showStatus(t('{count} zip(s) exportados para {folder}.', { count: made.length, folder }), 10)
    const { choice } = await ask({
      tone: 'info',
      title: t('Exportar para várias resoluções'),
      text,
      detail: t('No launcher: Adicionar UI Customizada, uma por resolução.'),
      choices: [
        { id: 'folder', label: t('Abrir pasta') },
        { id: 'ok', label: t('OK'), kind: 'primary' },
      ],
    })
    if (choice === 'folder') void api.openFolder(folder)
  }

  const presets = useMemo(() => {
    const list: Size[] = []
    for (const size of [...(info?.presets ?? []), ...(info ? [info.previewBase, info.base] : [])]) {
      if (!list.some((item) => sameSize(item, size))) list.push(size)
    }
    return list.sort((a, b) => a[0] - b[0] || a[1] - b[1])
  }, [info])

  return (
    <Modal
      title={t('Exportar para várias resoluções')}
      width={focused ? 1080 : 900}
      onClose={onClose}
      footer={
        <div className="flex w-full flex-wrap items-center gap-3">
          <div className="flex items-center gap-1 rounded-lg border border-border-input bg-input p-0.5" role="radiogroup" aria-label={t('O que vai em cada zip')}>
            {([[true, t('A UI inteira')], [false, t('Só o que muda')]] as const).map(([value, label]) => (
              <button
                key={label}
                role="radio"
                aria-checked={whole === value}
                data-testid={value ? 'zip-whole' : 'zip-changed'}
                onClick={() => setWhole(value)}
                className={`h-7 rounded-md px-3 text-[12.5px] transition-colors ${whole === value ? 'bg-accent text-on-accent' : 'text-muted hover:text-text'}`}
              >
                {label}
              </button>
            ))}
          </div>
          <label className="flex items-center gap-2 text-[12.5px] text-text" title={t('Mais um zip com a UI como você edita, para quem não sabe a própria resolução.')}>
            <input type="checkbox" checked={allResolution} onChange={(event) => setAllResolution(event.target.checked)} data-testid="zip-all" />
            {t('Também o "All Resolution"')}
          </label>
          <div className="flex-1" />
          <button className="btn" onClick={onClose}>
            {t('Cancelar')}
          </button>
          <button className="btn btn-primary" disabled={!ordered.length || !plan} onClick={() => void runExport()} data-testid="resolutions-export">
            <Icon name="package" size={15} />
            {t('Exportar {count} zip(s)…', { count: zipCount })}
          </button>
        </div>
      }
    >
      <div className="space-y-4" data-testid="resolutions-dialog">
        {error && <div className="hint-warning">{error}</div>}
        {!focused && (
          <>
            <p className="text-[12.5px] leading-snug text-muted">
              {t('O jogo não aumenta a interface: numa tela maior, cada janela continua do mesmo tamanho. O editor põe cada uma no mesmo lugar em cada resolução. Confira as prévias; se algo ficou fora do lugar, clique na resolução e arraste.')}
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[12.5px] text-muted">{t('Você edita em')}</span>
              <select
                className="field h-8 font-mono text-[12.5px]"
                value={base ? sizeKey(base) : ''}
                aria-label={t('Você edita em')}
                data-testid="resolution-base"
                onChange={(event) => {
                  const size = parseSize(event.target.value)
                  if (size) setBase(size)
                }}
              >
                {presets.map((size) => (
                  <option key={sizeKey(size)} value={sizeKey(size)}>
                    {sizeLabel(size)}
                  </option>
                ))}
              </select>
              <span className="mx-1 h-5 w-px bg-border" />
              {options.map((size) => (
                <Chip key={sizeKey(size)} on={checked.some((item) => sameSize(item, size))} onClick={() => toggle(size)} testId={`resolution-chip-${sizeKey(size)}`}>
                  <span className="font-mono">{sizeLabel(size)}</span>
                </Chip>
              ))}
              <button type="button" className="btn btn-ghost h-8 px-2.5 text-[12.5px]" onClick={() => void addCustom()} data-testid="resolution-custom">
                {t('+ personalizada')}
              </button>
            </div>
          </>
        )}
        <AnimatePresence mode="wait" initial={false}>
          {focused ? (
            <FocusView
              key={`focus-${focused.key}`}
              target={focused}
              layers={base ? layers[`${sizeKey(base)}|${focused.key}`] : undefined}
              cache={cache}
              onBack={() => setFocus(null)}
              onAdjust={(file, piece, point) => void adjust(file, piece, point)}
              onUndo={(file, piece) => void adjust(file, piece, null)}
              onUndoAll={async () => {
                await resolutionsApi.reset(focused.size)
                await afterChange(focused)
              }}
              onVariants={(action) => void variants(action)}
            />
          ) : (
            <motion.div key="grid" layout className="grid grid-cols-2 gap-3" data-testid="resolution-grid">
              {!plan && ordered.length > 0 && <div className="col-span-2 py-8 text-center text-muted">{t('Calculando…')}</div>}
              {!ordered.length && <div className="col-span-2 py-8 text-center text-muted">{t('Marque pelo menos uma resolução.')}</div>}
              {plan?.targets.map((target) => (
                <TargetCard key={target.key} target={target} layers={base ? layers[`${sizeKey(base)}|${target.key}`] : undefined} cache={cache} onOpen={() => setFocus(target.key)} />
              ))}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </Modal>
  )
}

export async function openResolutionsDialog(): Promise<void> {
  if (!(await saveBeforeProjectAction())) return
  await new Promise<void>((resolve) => {
    openDialog((close) => (
      <ResolutionsDialog
        onClose={() => {
          close()
          resolve()
        }}
      />
    ))
  })
}
