// Entrada, saída e troca de ordem animadas nas listas pequenas (AutoAnimate): projetos da tela
// inicial, banners, versões e listas dos diálogos. As listas virtualizadas grandes (Arquivos
// XML, Texturas, resultados de Textos) ficam sem: animar milhares de linhas pesa.
// O AutoAnimate já respeita "reduzir movimento" do sistema.
import { useAutoAnimate } from '@formkit/auto-animate/react'

export function useListAnimation<T extends Element = HTMLDivElement>() {
  const [ref] = useAutoAnimate<T>({ duration: 160, easing: 'ease-out' })
  return ref
}
