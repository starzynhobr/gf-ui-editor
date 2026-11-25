// Desliga o que denuncia "isto é um navegador": menu de contexto padrão, zoom da página com
// Ctrl+roda/Ctrl+±, recarregar (F5, Ctrl+R), imprimir, buscar, arrastar arquivos para a
// janela (abriria o arquivo no lugar do app) e seleção de texto fora de campos (no CSS).

const BLOCKED_WITH_CTRL = new Set(['r', 'p', 'f', 'g', 'u', 'j', 'h', 'o', 's', 'n', 't', 'w', '+', '-', '=', '0'])

export function installBrowserGuards(dev: boolean): void {
  window.addEventListener(
    'contextmenu',
    (event) => {
      const target = event.target as HTMLElement | null
      // Campos de texto mantêm o menu (copiar/colar); o resto usa os menus da casca.
      if (target?.closest('input, textarea')) return
      event.preventDefault()
    },
    true,
  )
  window.addEventListener('wheel', (event) => event.ctrlKey && event.preventDefault(), { passive: false })
  window.addEventListener(
    'keydown',
    (event) => {
      const key = event.key.toLowerCase()
      if (key === 'f5' || key === 'f3' || key === 'f7' || (key === 'f12' && !dev) || key === 'browserback' || key === 'browserforward') {
        event.preventDefault()
        return
      }
      if ((event.ctrlKey || event.metaKey) && !event.altKey && BLOCKED_WITH_CTRL.has(key)) {
        // Ctrl+Shift+N/O são atalhos do app (tratados em shortcuts.ts); só o padrão do navegador sai.
        event.preventDefault()
      }
      if (event.altKey && (key === 'arrowleft' || key === 'arrowright')) event.preventDefault()
    },
    true,
  )
  window.addEventListener('dragover', (event) => event.preventDefault())
  window.addEventListener('drop', (event) => event.preventDefault())
  // Clique do meio abriria rolagem automática / nova aba em links.
  window.addEventListener('auxclick', (event) => event.button === 1 && event.preventDefault())
  window.addEventListener('mousedown', (event) => event.button === 1 && event.preventDefault())
}
