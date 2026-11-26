// Barrinha da esquerda: Arquivos XML, Texturas, Elementos, Textos (Ctrl+1..4) e, embaixo,
// a engrenagem enxuta: Configurações… (idioma, tema e interface ficam lá), Como usar (F1), Novidades,
// Voltar para a clássica, Verificar atualizações e Sobre. Idioma e tema também saem pela paleta (Ctrl+K).
import { useT } from '../i18n'
import { useShell, type SidePage } from '../store'
import { openAbout } from './StzPill'
import { showPage } from '../actions'
import { openSettings } from '../settings/SettingsScreen'
import { checkForUpdates } from '../settings/updates'
import { openWhatsNew } from '../home/WhatsNewDialog'
import { backToClassic } from '../settings/interfaceSwitch'
import { openHowTo } from '../home/HowToDialog'
import { Icon } from '../ui/Icon'
import { openMenu } from '../ui/Menu'

export default function SideRail() {
  const t = useT()
  const page = useShell((state) => state.page)
  const view = useShell((state) => state.view)
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
        { label: t('Configurações…'), icon: 'settings', onClick: () => openSettings() },
        { label: t('Como usar'), icon: 'help', hint: 'F1', onClick: openHowTo },
        { separator: true },
        { label: t('Novidades desta versão'), icon: 'info', onClick: () => void openWhatsNew() },
        { label: t('Voltar para a clássica'), icon: 'undo', onClick: () => void backToClassic() },
        { label: t('Verificar atualizações…'), icon: 'sparkles', onClick: () => void checkForUpdates(true) },
        { separator: true },
        { label: t('Sobre o {name}…', { name: 'STZ GF UI' }), icon: 'info', onClick: openAbout },
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
      <button className="icon-button h-10 w-10" data-testid="settings-button" title={t('Configurações')} aria-label={t('Configurações')} onClick={(event) => settings(event.currentTarget)}>
        <Icon name="settings" size={20} />
      </button>
    </nav>
  )
}
