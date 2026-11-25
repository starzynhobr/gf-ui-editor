// Barrinha da esquerda: Arquivos XML, Texturas, Elementos, Textos (Ctrl+1..4) e, embaixo,
// a engrenagem com as configurações (idioma, interface, novidades).
import { api } from '../api'
import { LANGUAGES, setLanguage, useT } from '../i18n'
import { setShell, useShell, type SidePage } from '../store'
import { setUiMode, showPage } from '../actions'
import { openWhatsNew } from '../home/WhatsNewDialog'
import { Icon } from '../ui/Icon'
import { openMenu } from '../ui/Menu'

export default function SideRail() {
  const t = useT()
  const page = useShell((state) => state.page)
  const view = useShell((state) => state.view)
  const shell = useShell((state) => state.shell)
  const workspace = view === 'workspace'
  const buttons: [SidePage, string, string][] = [
    ['xml', 'file', t('Arquivos XML')],
    ['textures', 'image', t('Texturas')],
    ['elements', 'layers', t('Elementos')],
    ['texts', 'type', t('Textos')],
  ]

  const settings = (element: HTMLElement) => {
    const rect = element.getBoundingClientRect()
    openMenu({
      x: rect.right + 6,
      y: rect.top,
      items: [
        {
          label: t('Idioma'),
          icon: 'language',
          submenu: LANGUAGES.map(([code, label]) => ({
            label,
            checked: shell?.language === code,
            onClick: async () => {
              const state = await api.setLanguage(code)
              setLanguage(code)
              setShell(state)
            },
          })),
        },
        {
          label: t('Interface'),
          icon: 'layout',
          submenu: [
            { label: t('Clássica'), checked: shell?.ui_mode !== 'web', onClick: () => void setUiMode('classic') },
            { label: t('Nova (beta)'), checked: shell?.ui_mode === 'web', onClick: () => void setUiMode('web') },
          ],
        },
        { separator: true },
        { label: t('Novidades desta versão'), icon: 'sparkles', onClick: openWhatsNew },
      ],
    })
  }

  return (
    <nav className="flex w-12 shrink-0 flex-col items-center gap-1 border-r border-border bg-chrome py-2" data-testid="side-rail">
      {workspace &&
        buttons.map(([key, icon, label], index) => (
          <button
            key={key}
            className={`relative flex h-10 w-10 items-center justify-center rounded-lg transition-colors ${
              page === key ? 'bg-accent-soft text-accent-text' : 'text-icon hover:bg-hover hover:text-bright'
            }`}
            title={`${label} (Ctrl+${index + 1})`}
            aria-label={label}
            aria-pressed={page === key}
            onClick={() => showPage(key)}
          >
            {page === key && <span className="absolute top-2 bottom-2 left-[-4px] w-[3px] rounded-full bg-accent" />}
            <Icon name={icon} size={20} />
          </button>
        ))}
      <div className="flex-1" />
      <button className="icon-button h-10 w-10" title={t('Configurações')} aria-label={t('Configurações')} onClick={(event) => settings(event.currentTarget)}>
        <Icon name="settings" size={20} />
      </button>
    </nav>
  )
}
