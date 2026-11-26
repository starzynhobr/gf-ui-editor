// Importou um avulso: uma etiqueta com o nome "voa" do botão Importar até a linha do arquivo na
// lista do projeto (ou até o painel de arquivos, se a linha estiver fora da vista) e a linha
// pisca uma vez. Com "reduzir movimento", só o piscar.
import { animate } from 'motion/react'
import { nextFrame, prefersReducedMotion } from '../home/flight'

const norm = (path: string) => path.replace(/\\/g, '/').toLowerCase()

/** Linha do arquivo importado na lista (data-file é relativo à pasta da UI). */
export function findProjectRow(path: string): HTMLElement | null {
  const target = norm(path)
  for (const row of document.querySelectorAll<HTMLElement>('[data-file]')) {
    const relative = norm(row.dataset.file ?? '')
    if (relative && (target === relative || target.endsWith('/' + relative))) return row
  }
  return null
}

function landing(path: string): { rect: DOMRect; row: HTMLElement | null } | null {
  const row = findProjectRow(path)
  const panel = document.querySelector<HTMLElement>('[data-testid=files-panel]')
  for (const element of [row, panel]) {
    const rect = element?.getBoundingClientRect()
    if (rect && rect.width > 0 && rect.height > 0) return { rect, row: element === row ? row : null }
  }
  return null
}

export async function flyToProjectList(from: DOMRect | null, path: string, name: string): Promise<void> {
  // A lista é relida depois do setShell: espera ela desenhar a linha nova.
  await nextFrame()
  await nextFrame()
  const target = landing(path)
  if (!target) return
  const flash = () => {
    if (!target.row) return
    target.row.classList.add('gf-row-imported')
    window.setTimeout(() => target.row?.classList.remove('gf-row-imported'), 1400)
  }
  if (!from || prefersReducedMotion()) {
    flash()
    return
  }
  const chip = document.createElement('div')
  chip.className = 'gf-import-flight'
  chip.dataset.testid = 'import-flight'
  chip.textContent = name
  chip.style.left = `${from.left + from.width / 2}px`
  chip.style.top = `${from.top + from.height / 2}px`
  document.body.appendChild(chip)
  const end = target.row ? target.rect : new DOMRect(target.rect.left + 24, target.rect.top + 60, 120, 28)
  const dx = end.left + Math.min(end.width, 160) / 2 - (from.left + from.width / 2)
  const dy = end.top + end.height / 2 - (from.top + from.height / 2)
  try {
    await Promise.race([
      animate(chip, {
        x: [0, dx * 0.55, dx],
        y: [0, dy * 0.35 - 40, dy],
        scale: [1, 1.04, 0.82],
        opacity: [0.7, 1, 0.1],
      }, { duration: 0.62, ease: [0.3, 0.7, 0.2, 1], times: [0, 0.45, 1] }),
      new Promise((resolve) => window.setTimeout(resolve, 1000)),
    ])
  } finally {
    chip.remove()
    flash()
  }
}
