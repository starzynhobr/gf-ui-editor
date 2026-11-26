// Ponte da casca com o atlas DDS do canvas (web/src/atlas/index.ts, do Codex).
//
// O módulo entra pelo import.meta.glob: se o arquivo ainda não existe, a casca compila e os
// botões avisam que o atlas não está disponível; quando ele chegar, o Vite o inclui no build
// sem mudar nada aqui. Contrato esperado: openAtlas(index) e previewTexture(path).
export interface AtlasModule {
  openAtlas: (index: number) => unknown
  previewTexture: (path: string) => unknown
}

const modules = import.meta.glob<AtlasModule>('../atlas/index.ts')
let override: AtlasModule | null = null

/** Para testes: troca o módulo do atlas por um falso. */
export function setAtlasModule(module: AtlasModule | null): void {
  override = module
}

export async function atlasModule(): Promise<AtlasModule | null> {
  if (override) return override
  const load = modules['../atlas/index.ts']
  return load ? load() : null
}

export function atlasAvailable(): boolean {
  return override != null || '../atlas/index.ts' in modules
}
