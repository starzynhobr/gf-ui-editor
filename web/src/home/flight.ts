// Voo das Novidades: o diálogo encolhe até a pílula "Novidades" da barra (ou até a engrenagem,
// quando a barra não tem espaço) e volta dela ao reabrir. FLIP com o Motion: mede o retângulo
// do diálogo e o do destino, anima translação + escala com mola suave, o conteúdo some antes
// e a caixa termina transparente. Com "reduzir movimento" do sistema, só um fade.
import { animate } from 'motion/react'

const SPRING = { type: 'spring', visualDuration: 0.5, bounce: 0.14 } as const
/** Garante o fim mesmo se o quadro de animação não rodar (janela fora da tela, testes). */
const LIMIT = 1100

export function prefersReducedMotion(): boolean {
  return typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

/** Onde as notas pousam: a pílula, se estiver na barra; senão a engrenagem. */
export function landingRect(): DOMRect | null {
  const pill = document.querySelector<HTMLElement>('[data-testid=whats-new-pill][data-fits=true]')
  const gear = document.querySelector<HTMLElement>('[data-testid=settings-button]')
  for (const element of [pill, gear]) {
    const rect = element?.getBoundingClientRect()
    if (rect && rect.width > 0 && rect.height > 0) return rect
  }
  return null
}

export function nextFrame(): Promise<void> {
  return new Promise((resolve) => {
    let done = false
    const finish = () => {
      if (done) return
      done = true
      resolve()
    }
    requestAnimationFrame(() => requestAnimationFrame(finish))
    window.setTimeout(finish, 60)
  })
}

type Playback = { then: (onResolve: () => void, onReject?: () => void) => unknown }

function settle(animations: Playback[]): Promise<void> {
  const done = animations.map((animation) => new Promise<void>((resolve) => void animation.then(resolve, resolve)))
  return Promise.race([
    Promise.all(done).then(() => undefined),
    new Promise<void>((resolve) => window.setTimeout(resolve, LIMIT)),
  ])
}

/** Transformação que leva o centro e o tamanho de `from` até `to`. */
function delta(from: DOMRect, to: DOMRect) {
  return {
    x: to.left + to.width / 2 - (from.left + from.width / 2),
    y: to.top + to.height / 2 - (from.top + from.height / 2),
    scaleX: to.width / from.width,
    scaleY: to.height / from.height,
  }
}

function usable(rect: DOMRect | null): rect is DOMRect {
  return !!rect && rect.width > 0 && rect.height > 0
}

/**
 * Fecha voando até `target`. `onLanding` roda perto do fim (a pílula aparece enquanto a caixa
 * some, como se fosse ela mesma).
 */
export async function flyOut(box: HTMLElement, overlay: HTMLElement | null, target: DOMRect | null, onLanding?: () => void): Promise<void> {
  const from = box.getBoundingClientRect()
  const parts = Array.from(box.children) as HTMLElement[]
  if (prefersReducedMotion() || !usable(target) || !usable(from)) {
    onLanding?.()
    await settle([
      animate(box, { opacity: 0 }, { duration: 0.16 }),
      ...(overlay ? [animate(overlay, { opacity: 0 }, { duration: 0.16 })] : []),
    ])
    return
  }
  box.style.transformOrigin = '50% 50%'
  box.style.willChange = 'transform, opacity'
  const landing = window.setTimeout(() => onLanding?.(), 330)
  await settle([
    animate(parts, { opacity: 0 }, { duration: 0.14, ease: 'easeOut' }),
    animate(box, { ...delta(from, target), borderRadius: '24px' }, SPRING),
    animate(box, { opacity: [1, 1, 0] }, { duration: 0.5, times: [0, 0.6, 1], ease: 'easeIn' }),
    ...(overlay ? [animate(overlay, { opacity: 0 }, { duration: 0.32, ease: 'easeOut' })] : []),
  ])
  window.clearTimeout(landing)
  onLanding?.()
}

/** Abre crescendo a partir de `source` (a pílula), o caminho inverso do flyOut. */
export async function flyIn(box: HTMLElement, overlay: HTMLElement | null, source: DOMRect | null): Promise<void> {
  const to = box.getBoundingClientRect()
  const parts = Array.from(box.children) as HTMLElement[]
  if (prefersReducedMotion() || !usable(source) || !usable(to)) {
    await settle([animate(box, { opacity: [0, 1] }, { duration: 0.16 })])
    return
  }
  box.style.transformOrigin = '50% 50%'
  const start = delta(to, source)
  // Estado inicial já aplicado antes da pintura (a chamada vem de um useLayoutEffect): a caixa
  // nasce do tamanho da pílula, sem um quadro no tamanho final.
  box.style.transform = `translate(${start.x}px, ${start.y}px) scale(${start.scaleX}, ${start.scaleY})`
  box.style.opacity = '0'
  for (const part of parts) part.style.opacity = '0'
  if (overlay) overlay.style.opacity = '0'
  await settle([
    animate(box, { x: [start.x, 0], y: [start.y, 0], scaleX: [start.scaleX, 1], scaleY: [start.scaleY, 1] }, SPRING),
    animate(box, { borderRadius: ['24px', '12px'] }, { duration: 0.4, ease: 'easeOut' }),
    animate(box, { opacity: [0, 1] }, { duration: 0.18, ease: 'easeOut' }),
    animate(parts, { opacity: [0, 1] }, { duration: 0.22, delay: 0.26, ease: 'easeOut' }),
    ...(overlay ? [animate(overlay, { opacity: [0, 1] }, { duration: 0.3 })] : []),
  ])
  box.style.removeProperty('will-change')
}
