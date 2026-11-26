// Tamanho que anda até o novo valor (NumberFlow): "340 MB" → "230 MB" ao escolher uma opção do
// Limpar, ou sobe de zero quando o tamanho chega (lista de projetos). Curto (≈380 ms) para não
// cansar; com "reduzir movimento" do sistema o NumberFlow troca o número sem animar.
import NumberFlow from '@number-flow/react'
import { Fragment, useEffect, useState, type ReactNode } from 'react'
import { humanSize } from '../project/toolsApi'

export const SIZE_TIMING: EffectTiming = { duration: 380, easing: 'cubic-bezier(0.22, 0.8, 0.25, 1)' }
const FADE_TIMING: EffectTiming = { duration: 200, easing: 'ease-out' }

export interface SizeParts {
  value: number
  unit: string
  decimals: number
}

/** "340 MB", "1.2 GB", "12 KB" (formato do home.human_size do Python e do humanSize do front). */
export function parseSize(text: string): SizeParts | null {
  const match = /^\s*(\d+(?:[.,](\d+))?)\s*([A-Za-z]+)\s*$/.exec(text)
  if (!match) return null
  return { value: Number(match[1].replace(',', '.')), unit: match[3], decimals: match[2]?.length ?? 0 }
}

/** Bytes ou o texto pronto do Python. */
export function sizeParts(size: number | string): SizeParts | null {
  return parseSize(typeof size === 'number' ? humanSize(size) : size)
}

interface Props {
  value: number | string
  /** Começa em zero e sobe até o valor (quando o tamanho acaba de chegar). */
  countUp?: boolean
  className?: string
  testId?: string
}

export function AnimatedSize({ value, countUp = false, className, testId }: Props) {
  const parts = sizeParts(value)
  const text = typeof value === 'number' ? humanSize(value) : value
  const [shown, setShown] = useState(countUp ? 0 : (parts?.value ?? 0))
  const target = parts?.value ?? 0
  useEffect(() => {
    if (shown === target) return
    // Um quadro depois: o NumberFlow já montou com o valor anterior e anima a troca.
    const frame = requestAnimationFrame(() => setShown(target))
    return () => cancelAnimationFrame(frame)
  }, [target]) // eslint-disable-line react-hooks/exhaustive-deps
  if (!parts) return <span className={className} data-testid={testId} data-size={text}>{text}</span>
  return (
    <span className={`whitespace-nowrap tabular-nums ${className ?? ''}`} data-testid={testId} data-size={text}>
      <NumberFlow
        value={shown}
        locales="en-US"
        format={{ minimumFractionDigits: parts.decimals, maximumFractionDigits: parts.decimals, useGrouping: false }}
        suffix={` ${parts.unit}`}
        transformTiming={SIZE_TIMING}
        spinTiming={SIZE_TIMING}
        opacityTiming={FADE_TIMING}
        willChange
      />
    </span>
  )
}

/** Troca `{nome}` de um texto já traduzido por nós do React (ex.: um AnimatedSize no meio da frase). */
export function withNodes(text: string, nodes: Record<string, ReactNode>): ReactNode[] {
  return text.split(/(\{\w+\})/g).map((piece, index) => {
    const name = /^\{(\w+)\}$/.exec(piece)?.[1]
    return <Fragment key={index}>{name && name in nodes ? nodes[name] : piece}</Fragment>
  })
}
