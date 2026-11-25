# Canal beta

Revisão: **24/11/2026**. Decisão: caminho A ([D02](decisions.md)).

## Como funciona

- **Beta = Pre-release no GitHub**, com versão `X.Y.Z-beta.N` (ex.: `0.7.0-beta.1`).
- **Quem não marcou nada não recebe beta.** O atualizador consulta `releases/latest`, e o GitHub nunca devolve pre-release nesse endereço. O fallback sem API (`releases/latest/download/...`) também ignora pre-releases.
- **Quem marcou "Receber versões beta"** passa a consultar a lista de releases (`/releases`) e pega a mais nova, beta inclusive.
- **Promover:** publicar `X.Y.Z` estável. Todos recebem, inclusive quem está em `X.Y.Z-beta.N`.
- **Sair da beta:** desmarcar faz o editor esperar a próxima estável maior que a versão instalada; não rebaixa.

## Como usamos ([D12](decisions.md))

O roadmap todo é a **0.7.0**. Cada fase **completa** sai como `0.7.0-beta.N` para quem sugeriu testar (sem builds no meio da fase); a estável continua na 0.6.0 até o fim do roadmap, quando sai a 0.7.0. Correções no meio do caminho também viram a próxima beta, não uma estável.

## Caminho A: por que a primeira beta só vem depois

A 0.5.4 não tem a opção nem a consulta a pre-releases, então não consegue entrar no canal. A opção chega na **0.6.0 estável** ([Fase 0](roadmap.md#fase-0--base-do-canal-beta-060)), e as betas começam na seguinte: `0.7.0-beta.1` (Fase 1).

## O que implementar (Fase 0)

- [x] `parse_version`/`is_newer` entendem pre-release: `0.6.0-beta.1 < 0.6.0-beta.2 < 0.6.0`. **Hoje `0.6.0-beta.1` vira `(0, 6, 0, 1)`, que é maior que `0.6.0`**, e quem estivesse na beta nunca receberia a estável.
- [x] Opção "Receber versões beta" em Ajuda (desligada por padrão); ao marcar, verifica na hora.
- [x] Com a opção ligada: consultar `/releases`, ignorar rascunhos, escolher a maior versão; sem API (limite de 60/h), cair no fluxo atual de estáveis.
- [ ] Selo "beta" no Sobre e na janela de atualização (por enquanto o próprio número, `0.7.0-beta.1`, já diz; uma beta instalada liga a opção sozinha).
- [x] Testes do comparador, da escolha da release e da opção no menu.

## Para publicar uma beta

Ver [release](release.md#beta). Betas não vão para o Discord nem para o site ([D07](decisions.md)).
