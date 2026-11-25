import { useEffect, useState } from 'react'
import { call, type AppInfo } from './bridge'

// Casca provisória: o bloco 1 troca isto pela casca real (barra superior, lateral, telas).
export default function App() {
  const [info, setInfo] = useState<AppInfo | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    call<AppInfo>('app_info').then(setInfo, (e) => setError(String(e)))
  }, [])

  return (
    <div className="flex h-full items-center justify-center">
      <div className="rounded-lg border border-border bg-panel px-8 py-6">
        <div className="text-lg font-semibold text-bright">STZ GF UI — interface nova</div>
        <div className="mt-2 text-muted">
          {error ?? (info ? `versão ${info.version} · ${info.language}${info.dev ? ' · dev' : ''}` : 'conectando…')}
        </div>
      </div>
    </div>
  )
}
