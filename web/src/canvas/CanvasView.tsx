// Canvas do XML aberto (dono: bloco 1, canvas). A casca só monta <CanvasView path=... />.
export interface CanvasViewProps {
  /** Caminho absoluto do XML aberto, ou null (nada aberto). */
  path: string | null
}

export default function CanvasView({ path }: CanvasViewProps) {
  return (
    <div className="flex h-full items-center justify-center text-muted">
      {path ? `canvas: ${path}` : 'Nenhum XML aberto'}
    </div>
  )
}
