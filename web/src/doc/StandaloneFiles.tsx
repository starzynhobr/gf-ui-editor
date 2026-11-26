// Seção "Arquivos avulsos" no topo do painel de XMLs: XMLs abertos de fora do projeto, com a
// pasta de origem em cinza e um × para fechar o avulso (sai da lista; o arquivo fica no disco).
import { openXml } from '../actions'
import { useT } from '../i18n'
import { useShell } from '../store'
import { Icon } from '../ui/Icon'
import { closeStandaloneFile, fileName, folderOf } from './standalone'

export default function StandaloneFiles({ filter }: { filter: string }) {
  const t = useT()
  const shell = useShell((state) => state.shell)
  const all = shell?.standalone_paths ?? []
  const paths = all.filter((path) => path.toLowerCase().includes(filter))
  if (!all.length) return null
  return (
    <section className="gf-standalone-files" aria-label={t('Arquivos avulsos')} data-testid="standalone-files">
      <div className="flex h-7 items-center gap-1.5 px-3">
        <span className="section-label flex-1">{t('ARQUIVOS AVULSOS · {count}', { count: all.length })}</span>
      </div>
      <div className="max-h-40 overflow-auto pb-1">
        {paths.map((path) => {
          const current = path === shell?.open_path
          return (
            <div
              key={path}
              className={`group flex h-8 items-center gap-2 pr-1.5 pl-3 ${current ? 'bg-selected text-bright' : 'hover:bg-hover'}`}
              data-standalone-row={path}
            >
              <button
                title={path}
                aria-current={current ? 'true' : undefined}
                data-standalone-file={path}
                className="flex min-w-0 flex-1 items-center gap-2 text-left"
                onClick={() => void openXml(path)}
              >
                <span className="gf-standalone-file-icon"><Icon name="file" size={13} /></span>
                <span className="min-w-0 flex-1 truncate">
                  <span className={current ? 'text-accent-text' : 'text-text'}>{fileName(path)}</span>
                  <span className="ml-1.5 text-[11px] text-disabled">{folderOf(path)}</span>
                </span>
              </button>
              <button
                className={`icon-button h-6 w-6 ${current ? '' : 'opacity-0 group-hover:opacity-100 focus-visible:opacity-100'}`}
                title={t('Fechar o avulso (o arquivo continua no disco)')}
                aria-label={t('Fechar {name}', { name: fileName(path) })}
                data-testid="standalone-close"
                onClick={() => void closeStandaloneFile(path)}
              >
                <Icon name="x" size={13} />
              </button>
            </div>
          )
        })}
      </div>
    </section>
  )
}
