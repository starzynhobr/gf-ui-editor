import { openXml } from '../actions'
import { t } from '../i18n'
import { useShell } from '../store'

export default function StandaloneFiles({ filter }: { filter: string }) {
  const shell = useShell((state) => state.shell)
  const paths = shell?.standalone_paths?.filter((path) => path.toLowerCase().includes(filter)) ?? []
  if (!paths.length) return null
  return (
    <section className="max-h-36 shrink-0 overflow-auto border-t border-border px-3 py-1" aria-label={t('Arquivos avulsos')}>
      <div className="text-muted">{t('Arquivos avulsos')}</div>
      {paths.map((path) => (
        <button key={path} title={path} aria-current={path === shell?.open_path ? 'true' : undefined}
          data-standalone-file={path} className="block w-full truncate text-left hover:bg-hover aria-[current=true]:text-accent-text"
          onClick={() => void openXml(path)}>
          {path.split(/[\\/]/).pop()}
        </button>
      ))}
    </section>
  )
}
