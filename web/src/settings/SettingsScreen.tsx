// Configurações da interface nova (engrenagem → "Configurações…"). Os mesmos itens dos menus da
// clássica (Idioma, Interface, Navegação do canvas, Resolução do jogo, Ajuda → atualizações…) e as
// mesmas preferências: o que muda aqui vale nas duas interfaces.
import * as Switch from '@radix-ui/react-switch'
import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { create } from 'zustand'
import { api, errorText } from '../api'
import { refreshShell } from '../actions'
import { applyCanvasPreference } from '../doc/store'
import { openWhatsNew } from '../home/WhatsNewDialog'
import { LANGUAGES, setLanguage, t, useT } from '../i18n'
import { THEMES, loadUiState, setTheme, useUi, type ThemeName } from '../shell/uiState'
import { setShell, showStatus, useShell } from '../store'
import { message } from '../ui/dialogs'
import { Icon } from '../ui/Icon'
import { Select } from '../ui/Select'
import { checkForUpdates } from './updates'
import { settingsApi, type SettingName, type SettingsState, type SettingsValues } from './settingsApi'
import './settings.css'

export type SettingsSection = 'general' | 'editor' | 'screen' | 'publish' | 'updates'

interface SettingsUi {
  open: boolean
  section: SettingsSection
  /** Sobe quando uma opção do preview muda com o canvas aberto: a casca remonta o canvas. */
  canvasEpoch: number
}

export const useSettings = create<SettingsUi>(() => ({ open: false, section: 'general', canvasEpoch: 0 }))

export function openSettings(section: SettingsSection = 'general'): void {
  useSettings.setState({ open: true, section })
}

export function closeSettings(): void {
  useSettings.setState({ open: false })
}

// Opções do preview que o canvas também mostra na barra dele.
const CANVAS_KEYS: Partial<Record<SettingName, 'resolution' | 'background' | 'savedPositions' | 'character'>> = {
  game_resolution: 'resolution',
  background_mode: 'background',
  canvas_saved_positions: 'savedPositions',
  canvas_character: 'character',
}

/** Avisa quem quiser ouvir (canvas: estilo de navegação) que uma configuração mudou. */
function announce(name: SettingName, value: unknown): void {
  window.dispatchEvent(new CustomEvent('gf:settings-changed', { detail: { name, value } }))
}

// ---- peças da tela --------------------------------------------------------------------------

function Toggle({ name, checked, onChange, disabled }: { name: string; checked: boolean; onChange: (value: boolean) => void; disabled?: boolean }) {
  return (
    <Switch.Root
      className="gf-switch"
      checked={checked}
      disabled={disabled}
      onCheckedChange={onChange}
      data-setting={name}
      aria-label={name}
    >
      <Switch.Thumb className="gf-switch-thumb" />
    </Switch.Root>
  )
}

function Row({ title, text, children, testId }: { title: string; text?: ReactNode; children?: ReactNode; testId?: string }) {
  return (
    <div className="gf-settings-row" data-testid={testId}>
      <div className="min-w-0 flex-1">
        <div className="text-bright">{title}</div>
        {text && <div className="mt-0.5 text-[12px] leading-snug text-muted">{text}</div>}
      </div>
      {children && <div className="flex shrink-0 items-center gap-2">{children}</div>}
    </div>
  )
}

function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-2">
      <div className="section-label px-1">{title}</div>
      <div className="gf-settings-group">{children}</div>
    </section>
  )
}

function Segmented<T extends string>({ name, value, options, onChange }: {
  name: string
  value: T
  options: { value: T; label: string; icon?: ReactNode }[]
  onChange: (value: T) => void
}) {
  return (
    <div className="gf-segmented" role="radiogroup" aria-label={name} data-setting={name}>
      {options.map((option) => (
        <button
          key={option.value}
          role="radio"
          aria-checked={option.value === value}
          className="gf-segment"
          data-value={option.value}
          onClick={() => option.value !== value && onChange(option.value)}
        >
          {option.value === value && (
            <motion.span layoutId={`segment-${name}`} className="gf-segment-active" transition={{ type: 'spring', stiffness: 520, damping: 38 }} />
          )}
          <span className="relative flex items-center gap-1.5">
            {option.icon}
            {option.label}
          </span>
        </button>
      ))}
    </div>
  )
}

const THEME_ICON: Record<ThemeName, ReactNode> = {
  dark: (
    <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
      <path d="M13 9.5A5.5 5.5 0 0 1 6.5 3a5.5 5.5 0 1 0 6.5 6.5Z" fill="currentColor" />
    </svg>
  ),
  midnight: (
    <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
      <path d="M8 1.5l1.4 3.6L13 6.5 9.4 7.9 8 11.5 6.6 7.9 3 6.5l3.6-1.4z M12.5 10.5l.6 1.4 1.4.6-1.4.6-.6 1.4-.6-1.4-1.4-.6 1.4-.6z" fill="currentColor" />
    </svg>
  ),
  light: (
    <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
      <circle cx="8" cy="8" r="3" fill="currentColor" />
      <path d="M8 1v2M8 13v2M1 8h2M13 8h2M3 3l1.4 1.4M11.6 11.6 13 13M3 13l1.4-1.4M11.6 4.4 13 3" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  ),
  cappuccino: (
    <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
      <path d="M2.5 6.5h9v3a4 4 0 0 1-4 4h-1a4 4 0 0 1-4-4z" fill="currentColor" />
      <path d="M11.5 7.5h.8a1.7 1.7 0 0 1 0 3.4h-1.1" fill="none" stroke="currentColor" strokeWidth="1.3" />
      <path d="M5.5 1.8c-.6.7.6 1.4 0 2.4M8.5 1.8c-.6.7.6 1.4 0 2.4" fill="none" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round" />
    </svg>
  ),
  rosa: (
    <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
      <path d="M8 14s-5.5-3.3-5.5-7.2A3 3 0 0 1 8 4.9a3 3 0 0 1 5.5 1.9C13.5 10.7 8 14 8 14Z" fill="currentColor" />
    </svg>
  ),
}

// ---- a tela -----------------------------------------------------------------------------------

function SettingsPanel() {
  useT()
  const section = useSettings((state) => state.section)
  const theme = useUi((state) => state.theme)
  const [state, setState] = useState<SettingsState | null>(null)
  // Mudanças em fila: duas trocas rápidas gravam as duas, na ordem (nenhuma é descartada).
  const queue = useRef<Promise<void>>(Promise.resolve())

  useEffect(() => {
    void settingsApi.state().then(setState, (error) => void message('error', t('Configurações'), errorText(error)))
    // O atualizador (pular versão) e outros fluxos avisam quando o que a tela mostra mudou.
    const refresh = () => void settingsApi.state().then(setState).catch(() => undefined)
    window.addEventListener('gf:settings-refresh', refresh)
    return () => window.removeEventListener('gf:settings-refresh', refresh)
  }, [])

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      // Com uma pergunta aberta por cima, o Esc é dela.
      if (event.key === 'Escape' && document.querySelectorAll('[role="dialog"]').length <= 1) {
        event.stopPropagation()
        closeSettings()
      }
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [])

  function change<K extends SettingName>(name: K, value: SettingsValues[K]): Promise<void> {
    setState((current) => (current ? { ...current, values: { ...current.values, [name]: value } } : current)) // resposta imediata
    queue.current = queue.current.then(() => apply(name, value))
    return queue.current
  }

  async function apply<K extends SettingName>(name: K, value: SettingsValues[K]): Promise<void> {
    try {
      const path = useShell.getState().shell?.open_path
      const canvasKey = CANVAS_KEYS[name]
      if (canvasKey && path) {
        // Com um XML aberto, passa pelo canvas: o preview é recalculado na hora (mesma ponte da barra).
        await applyCanvasPreference(path, canvasKey, value as string | boolean)
        setState(await settingsApi.state())
        useSettings.setState((current) => ({ canvasEpoch: current.canvasEpoch + 1 }))
      } else if (name === 'language') {
        const shellState = await api.setLanguage(value as string)
        setLanguage(value as string)
        setShell(shellState)
        setState(await settingsApi.state())
      } else {
        setState(await settingsApi.set(name, value))
      }
      announce(name, value)
      if (name === 'ui_mode') {
        await refreshShell()
        showStatus(t('A interface escolhida vale na próxima vez que o editor abrir.'), 8)
      }
      if (name === 'publish_on_save' || name === 'publish_confirmed') await refreshShell()
      if (name === 'beta_updates' && value === true) void checkForUpdates(true) // como a clássica ao entrar no canal
    } catch (error) {
      setState(await settingsApi.state().catch(() => null))
      await message('warning', t('Configurações'), errorText(error))
    }
  }

  async function reset(what: 'skipped_update' | 'manifest_seen' | 'layout'): Promise<void> {
    setState(await settingsApi.reset(what))
    if (what === 'layout') await loadUiState()
    showStatus(t('Pronto.'), 4)
  }

  async function chooseGameDir(): Promise<void> {
    if (!state) return
    const chosen = await settingsApi.pickGameDir(state.values.game_dir || state.game_dir_default)
    if (chosen) await change('game_dir', chosen)
  }

  async function chooseBackground(mode: string): Promise<void> {
    if (!state) return
    if (mode === 'choose') {
      await settingsApi.chooseBackground()
      setState(await settingsApi.state())
      useSettings.setState((current) => ({ canvasEpoch: current.canvasEpoch + 1 }))
      return
    }
    await change('background_mode', mode as SettingsValues['background_mode'])
  }

  const nav: [SettingsSection, string, string][] = [
    ['general', 'settings', t('Geral')],
    ['editor', 'pencil', t('Editor')],
    ['screen', 'image', t('Tela')],
    ['publish', 'send', t('Envio')],
    ['updates', 'sparkles', t('Atualizações')],
  ]

  const values = state?.values
  const resolutionOptions = state
    ? [
        { value: 'game', label: t('Igual ao jogo (client.ini)') },
        { value: 'off', label: t('Sem tela do jogo (janela solta)') },
        ...state.resolutions.map((value) => ({ value, label: value.replace('x', ' × ') })),
        ...(values && !['game', 'off', ...state.resolutions].includes(values.game_resolution)
          ? [{ value: values.game_resolution, label: values.game_resolution.replace('x', ' × ') }]
          : []),
      ]
    : []

  const body: Record<SettingsSection, () => ReactNode> = {
    general: () =>
      values && state && (
        <>
          <Group title={t('Aparência')}>
            <Row title={t('Idioma')}>
              <Select
                className="w-[200px]"
                label={t('Idioma')}
                name="language"
                value={values.language}
                options={LANGUAGES.map(([value, label]) => ({ value, label }))}
                onChange={(value) => void change('language', value)}
              />
            </Row>
            <Row title={t('Tema')}>
              <Segmented
                name="web_theme"
                value={theme}
                options={THEMES.map((value) => ({
                  value,
                  icon: THEME_ICON[value],
                  label: { dark: t('Escuro'), midnight: t('Meia-noite'), light: t('Claro'), cappuccino: t('Cappuccino'), rosa: t('Rosa') }[value],
                }))}
                onChange={(value) => {
                  setTheme(value)
                  setState({ ...state, values: { ...values, web_theme: value } })
                }}
              />
            </Row>
            <Row title={t('Interface')} text={t('A interface escolhida vale na próxima vez que o editor abrir.')}>
              <Segmented
                name="ui_mode"
                value={values.ui_mode}
                options={[
                  { value: 'classic', label: t('Clássica') },
                  { value: 'web', label: t('Nova (beta)') },
                ]}
                onChange={(value) => void change('ui_mode', value)}
              />
            </Row>
          </Group>
          <Group title={t('Rever e limpar')}>
            <Row
              title={t('Versão pulada')}
              text={state.review.skipped_update
                ? t('A {version} não é mais oferecida ao abrir.', { version: state.review.skipped_update })
                : t('Nenhuma versão pulada.')}
            >
              <button className="btn" disabled={!state.review.skipped_update} onClick={() => void reset('skipped_update')}>
                {t('Oferecer de novo')}
              </button>
            </Row>
            <Row title={t('Avisos já vistos')} text={t('{count} aviso(s) do STZ Labs já mostrados.', { count: state.review.manifest_seen })}>
              <button className="btn" disabled={!state.review.manifest_seen} onClick={() => void reset('manifest_seen')}>
                {t('Mostrar de novo')}
              </button>
            </Row>
            <Row title={t('Painéis e colunas')} text={t('Larguras dos painéis, ordem das seções da lista e colunas da árvore.')}>
              <button className="btn" disabled={!state.review.layout} onClick={() => void reset('layout')} data-testid="settings-reset-layout">
                {t('Restaurar')}
              </button>
            </Row>
          </Group>
        </>
      ),
    editor: () =>
      values && (
        <Group title={t('Editor')}>
          <Row
            title={t('Navegação do canvas')}
            text={{
              corel: t('Roda: zoom · botão do meio ou Espaço+arrastar: mover'),
              paintnet: t('Roda: rolar · Shift+roda: para os lados · Ctrl+roda: zoom'),
              photoshop: t('Roda: rolar · Ctrl+roda: para os lados · Alt+roda: zoom'),
            }[values.navigation_style]}
          >
            <Select
              className="w-[200px]"
              label={t('Navegação do canvas')}
              name="navigation_style"
              value={values.navigation_style}
              options={[
                { value: 'corel', label: t('Estilo CorelDRAW') },
                { value: 'paintnet', label: t('Estilo Paint.NET') },
                { value: 'photoshop', label: t('Estilo Photoshop') },
              ]}
              onChange={(value) => void change('navigation_style', value as SettingsValues['navigation_style'])}
            />
          </Row>
          <Row title={t('Oferecer um projeto ao abrir um XML solto')} text={t('Pergunta se você quer criar um projeto antes de editar um arquivo solto.')}>
            <Toggle name="offer_project_on_open" checked={values.offer_project_on_open} onChange={(value) => void change('offer_project_on_open', value)} />
          </Row>
        </Group>
      ),
    screen: () =>
      values && state && (
        <Group title={t('Preview do jogo')}>
          <Row title={t('Resolução do jogo')}>
            <Select
              className="w-[260px]"
              label={t('Resolução do jogo')}
              name="game_resolution"
              value={values.game_resolution}
              options={resolutionOptions}
              onChange={(value) => void change('game_resolution', value)}
            />
          </Row>
          <Row title={t('Fundo')} text={state.has_custom_background ? state.game_background : undefined}>
            <Select
              className="w-[260px]"
              label={t('Fundo')}
              name="background_mode"
              value={values.background_mode}
              options={[
                { value: 'builtin', label: t('Fundo do jogo (embutido)') },
                ...(state.has_custom_background ? [{ value: 'custom', label: t('Captura própria') }] : []),
                { value: 'choose', label: t('Captura própria…') },
                { value: 'none', label: t('Sem fundo') },
              ]}
              onChange={(value) => void chooseBackground(value)}
            />
          </Row>
          <Row title={t('Usar posições salvas do User.ini')}>
            <Toggle name="canvas_saved_positions" checked={values.canvas_saved_positions} onChange={(value) => void change('canvas_saved_positions', value)} />
          </Row>
          <Row title={t('Personagem')}>
            <Toggle name="canvas_character" checked={values.canvas_character} onChange={(value) => void change('canvas_character', value)} />
          </Row>
        </Group>
      ),
    publish: () =>
      values && state && (
        <>
          <Group title={t('Pasta do jogo')}>
            <Row
              title={values.game_dir || state.game_dir_default || t('Nenhuma pasta escolhida')}
              text={
                values.game_dir && !state.game_dir_valid
                  ? t('Esta pasta não parece ser a do jogo (sem client.ini ou Launcher.ini).')
                  : t('Usada ao criar projetos novos e ao abrir XMLs soltos.')
              }
              testId="settings-game-dir"
            >
              {values.game_dir && (
                <button className="btn btn-ghost" onClick={() => void change('game_dir', '')}>
                  {t('Usar a padrão')}
                </button>
              )}
              <button className="btn" onClick={() => void chooseGameDir()}>
                {t('Escolher…')}
              </button>
            </Row>
          </Group>
          <Group title={t('Enviar para o jogo')}>
            <Row title={t('Enviar para o jogo ao salvar')}>
              <Toggle name="publish_on_save" checked={values.publish_on_save} onChange={(value) => void change('publish_on_save', value)} />
            </Row>
            <Row title={t('Confirmar antes do primeiro envio')} text={t('Mostra de novo o aviso de onde a UI vai ser gravada.')}>
              <Toggle name="publish_confirmed" checked={!values.publish_confirmed} onChange={(value) => void change('publish_confirmed', !value)} />
            </Row>
          </Group>
        </>
      ),
    updates: () =>
      values && state && (
        <>
          <div className="gf-settings-hero">
            <div className="min-w-0 flex-1">
              <div className="text-[15px] font-semibold text-bright">STZ GF UI {state.version}</div>
              <div className="text-[12px] text-muted">
                {state.can_install ? t('Instalado') : t('Rodando pelo código-fonte')}
                {state.beta_build ? ' · beta' : ''}
              </div>
            </div>
            <button className="btn" onClick={openWhatsNew}>
              {t('Novidades desta versão')}
            </button>
            <button className="btn btn-primary" data-testid="settings-check-updates" onClick={() => void checkForUpdates(true)}>
              {t('Verificar atualizações…')}
            </button>
          </div>
          <Group title={t('Atualizações')}>
            <Row title={t('Verificar ao iniciar')} text={t('Uma vez por dia, também lê os avisos do STZ Labs.')}>
              <Toggle name="auto_update_check" checked={values.auto_update_check} onChange={(value) => void change('auto_update_check', value)} />
            </Row>
            <Row
              title={t('Receber versões beta')}
              text={t('Também oferece versões em teste, antes de virarem estáveis. Desmarque para voltar a receber só as estáveis.')}
            >
              <Toggle name="beta_updates" checked={values.beta_updates} onChange={(value) => void change('beta_updates', value)} />
            </Row>
          </Group>
        </>
      ),
  }

  return (
    <motion.div
      className="gf-settings-backdrop"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0, transition: { duration: 0.12 } }}
      onMouseDown={(event) => event.target === event.currentTarget && closeSettings()}
    >
      <motion.div
        className="gf-settings"
        role="dialog"
        aria-modal="true"
        aria-label={t('Configurações')}
        data-testid="settings"
        initial={{ opacity: 0, y: 14, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 8, scale: 0.98, transition: { duration: 0.12 } }}
        transition={{ type: 'spring', stiffness: 380, damping: 32 }}
      >
        <nav className="gf-settings-nav">
          <div className="px-3 pt-1 pb-3 text-[15px] font-semibold text-bright">{t('Configurações')}</div>
          {nav.map(([key, icon, label]) => (
            <button
              key={key}
              className="gf-settings-nav-item"
              aria-current={section === key ? 'page' : undefined}
              data-section={key}
              onClick={() => useSettings.setState({ section: key })}
            >
              {section === key && <motion.span layoutId="settings-nav" className="gf-settings-nav-active" transition={{ type: 'spring', stiffness: 500, damping: 40 }} />}
              <Icon name={icon} size={16} className="relative" />
              <span className="relative">{label}</span>
            </button>
          ))}
        </nav>
        <div className="flex min-w-0 flex-1 flex-col">
          <div className="flex items-center gap-2 border-b border-border px-6 py-3">
            <div className="flex-1 text-[14px] font-semibold text-bright">{nav.find(([key]) => key === section)?.[2]}</div>
            <button className="icon-button" onClick={closeSettings} aria-label={t('Fechar')} data-testid="settings-close">
              <Icon name="x" />
            </button>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
            <AnimatePresence mode="wait" initial={false}>
              <motion.div
                key={section}
                className="space-y-6"
                data-testid={`settings-${section}`}
                initial={{ opacity: 0, x: 10 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -6, transition: { duration: 0.08 } }}
                transition={{ duration: 0.16, ease: 'easeOut' }}
              >
                {state ? body[section]() : <div className="h-40" />}
              </motion.div>
            </AnimatePresence>
          </div>
        </div>
      </motion.div>
    </motion.div>
  )
}

/** Host da tela (montado uma vez na casca). */
export default function SettingsHost() {
  const open = useSettings((state) => state.open)
  return <AnimatePresence>{open && <SettingsPanel key="settings" />}</AnimatePresence>
}
