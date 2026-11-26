import { useState } from 'react'
import { Children, isValidElement } from 'react'
import { Select, type SelectOption } from '../ui/Select'
import { Icon } from '../ui/Icon'
import type { ReactNode } from 'react'
import type { CanvasPreference, CanvasPreferences, CanvasRect } from '../bridge'
import { useT } from '../i18n'

interface Props {
  preferences: CanvasPreferences
  screen: CanvasRect
  busy: boolean
  showCharacter: boolean
  layers: string[]
  inProject: boolean
  buttonState?: string
  buttonUvs?: Record<string, CanvasRect>
  scale: number
  onPreference: (key: CanvasPreference, value: string | boolean) => Promise<boolean>
  onBackground: () => void
  onLayers: (action: 'default' | 'clear') => void
  onButtonState: (state?: string) => void
  onZoom: (factor: number) => void
  onResetZoom: () => void
  onFit: () => void
  children?: ReactNode
}

function ToolbarSelect({ label, caption, icon, active, value, disabled, onChange, children }: {
  label: string; caption?: string; icon: string; active?: boolean; value: string; disabled?: boolean
  onChange: (value: string) => void; children: ReactNode
}) {
  // Lista no tema do app (ui/Select, Radix): as <option> filhas viram as opções.
  const options: SelectOption[] = Children.toArray(children).flatMap((child) => {
    if (!isValidElement<{ value?: string; children?: ReactNode; disabled?: boolean }>(child)) return []
    const text = Children.toArray(child.props.children).join('')
    return [{ value: String(child.props.value ?? text), label: text, disabled: child.props.disabled }]
  })
  // Com legenda (Tela, Fundo, Camadas, Texto), o próprio botão mostra o resumo, como antes.
  return <div className="gf-canvas-select-themed">
    <Select size="sm" label={label} value={value} disabled={disabled} active={active} options={options} onChange={onChange}
      display={caption} />
    <Icon name={icon} size={14} className="gf-canvas-select-icon" />
  </div>
}

export function AtlasResizeCheckbox({ label, checked, disabled, onChange }: {
  label: string; checked: boolean; disabled: boolean; onChange: (value: boolean) => void
}) {
  return <label className="gf-atlas-resize"><input type="checkbox" checked={checked} disabled={disabled}
    onChange={(event) => onChange(event.target.checked)} />{label}</label>
}

export function CanvasToolbar({
  preferences, screen: [, , width, height], busy, showCharacter, layers, inProject,
  buttonState, buttonUvs, scale, onPreference, onBackground, onLayers, onButtonState,
  onZoom, onResetZoom, onFit, children,
}: Props) {
  const t = useT()
  const [custom, setCustom] = useState<string | null>(null)
  const { resolution, presets, background, backgroundPath, savedPositions, character, text, outlines, ids } = preferences
  const preview = resolution !== 'off'
  const isCustom = preview && resolution !== 'game' && !presets.some(([w, h]) => resolution === w + 'x' + h)
  const screenLabel = preview
    ? t('Tela {width} × {height}', { width, height }) + (resolution === 'game' ? ' · ' + t('jogo') : '')
    : t('Sem tela do jogo')
  const backgroundName = backgroundPath.split(/[\\/]/).at(-1)
  return <>
    <div className="gf-canvas-toolbar">
      <button aria-pressed={outlines} disabled={busy} onClick={() => void onPreference('outlines', !outlines)}>
        <Icon name="layout" size={14} />{t('Contornos')}
      </button>
      <button aria-label={t('Mostrar identificadores')} title={t('Mostrar identificadores')} aria-pressed={ids} disabled={busy}
        onClick={() => void onPreference('ids', !ids)}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75"
          strokeLinecap="round" aria-hidden="true">
          <path d="M9 4 7 20M17 4l-2 16M4 9h16M3 15h16" />
        </svg>
      </button>
      <ToolbarSelect icon="layout" label={t('Tela')} caption={screenLabel} value={isCustom ? 'current' : resolution} disabled={busy}
        onChange={(value) => {
          if (value === 'custom') setCustom(width + 'x' + height)
          else {
            setCustom(null)
            void onPreference('resolution', value)
          }
        }}>
        <option value="game">{resolution === 'game' ? t('Igual ao jogo ({width} × {height})', { width, height }) : t('Igual ao jogo (client.ini)')}</option>
        <option value="off">{t('Sem tela do jogo (janela solta)')}</option>
        {presets.map(([w, h]) => <option key={w + 'x' + h} value={w + 'x' + h}>{w} × {h}</option>)}
        {isCustom && <option value="current" disabled>{width} × {height}</option>}
        <option value="custom">{t('Personalizada…')}</option>
      </ToolbarSelect>
      {custom !== null && <form className="gf-canvas-resolution-form" onSubmit={async (event) => {
        event.preventDefault()
        if (await onPreference('resolution', custom)) setCustom(null)
      }}>
        <input autoFocus required pattern="\s*\d+\s*[xX× ]\s*\d+\s*" aria-label={t('Largura × altura (ex.: 1366x768):')} value={custom}
          onKeyDown={(event) => { if (event.key === 'Escape') setCustom(null) }}
          onChange={(event) => setCustom(event.target.value)} />
        <button type="submit" disabled={busy}>{t('Aplicar')}</button>
        <button type="button" onClick={() => setCustom(null)}>{t('Cancelar')}</button>
      </form>}
      <ToolbarSelect icon="image" label={t('Fundo')} caption={t('Fundo')} active={preview && background !== 'none'} value={background}
        disabled={busy} onChange={(value) => value === 'choose' ? onBackground() : void onPreference('background', value)}>
        <option value="builtin">{t('Fundo do jogo (embutido)')}</option>
        {backgroundName && <option value="custom">{backgroundName}</option>}
        <option value="choose">{t('Captura própria…')}</option>
        <option value="none">{t('Sem fundo')}</option>
      </ToolbarSelect>
      <button aria-pressed={savedPositions} disabled={busy}
        title={t('Usar posições salvas do User.ini')} onClick={() => void onPreference('savedPositions', !savedPositions)}>
        <Icon name="settings" size={14} />User.ini
      </button>
      {showCharacter && <button aria-pressed={character} disabled={busy}
        onClick={() => void onPreference('character', !character)}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75"
          strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <circle cx="12" cy="8" r="4" /><path d="M5 21v-2a5 5 0 0 1 5-5h4a5 5 0 0 1 5 5v2" />
        </svg>{t('Personagem')}
      </button>}
      <ToolbarSelect icon="layers" label={t('Camadas')} caption={t('Camadas')} active={layers.length > 0} value="" disabled={busy || !inProject}
        onChange={(value) => { if (value === 'default' || value === 'clear') onLayers(value) }}>
        <option value="" disabled>{t('Camadas')}</option>
        <option value="default">{t('Montar HUD padrão')}</option>
        <option value="clear" disabled={!layers.length}>{t('Limpar camadas')}</option>
        {layers.map((name) => <option key={name} disabled>{name}</option>)}
      </ToolbarSelect>
      <ToolbarSelect icon="type" label={t('Texto')} caption={t('Texto')} active={text !== 'off'} value={text} disabled={busy}
        onChange={(value) => void onPreference('text', value)}>
        <option value="off">{t('Desligado')}</option>
        <option value="game">{t('Textos do jogo')}</option>
        <option value="xml">{t('Só o texto do XML')}</option>
        <option value="short">{t('Amostra curta')}</option>
        <option value="long">{t('Amostra longa')}</option>
      </ToolbarSelect>
      {buttonUvs && ['FocusUV', 'DownUV', 'DisableUV'].some((state) => buttonUvs[state]) &&
        <ToolbarSelect icon="eye" label={t('Normal')} value={buttonState ?? ''} onChange={(value) => onButtonState(value || undefined)}>
          <option value="">{t('Normal')}</option>
          {buttonUvs.FocusUV && <option value="FocusUV">{t('Foco')}</option>}
          {buttonUvs.DownUV && <option value="DownUV">{t('Pressionado')}</option>}
          {buttonUvs.DisableUV && <option value="DisableUV">{t('Desativado')}</option>}
        </ToolbarSelect>}
      {children}
    </div>
    <div className="gf-canvas-zoom">
      <button aria-label={t('Diminuir zoom')} onClick={() => onZoom(1 / 1.15)}>−</button>
      <button title={t('Voltar a 100% (Ctrl+0)')} data-testid="canvas-zoom-reset" onClick={onResetZoom}>{Math.round(scale * 100)}%</button>
      <button aria-label={t('Aumentar zoom')} onClick={() => onZoom(1.15)}>+</button>
      <button data-testid="canvas-fit" onClick={onFit}><Icon name="focus" size={14} />{t('Enquadrar')}</button>
    </div>
  </>
}
