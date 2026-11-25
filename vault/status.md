# Estado atual

Revisão: **24/11/2026**. Última release publicada: **0.6.0** (24/11/2026).

## Beta 0.7.0-beta.1 publicada (24/11/2026, pre-release; Fase 1)

- Clique e setas na lista de XMLs abrem no canvas sem sair da lista; duplo clique/Enter vão para Elementos.
- Ctrl+1..4 nas seções da barra lateral (atalho na dica de cada ícone).
- Clique na porcentagem do zoom ou Ctrl+0 → 100%.
- Botão Home no canto superior esquerdo, funcionando sempre.
- Instalador registra o editor em "Abrir com" dos `.xml` (HKCU, sem virar padrão).
- Atualizar (Ctrl+R) recarrega o XML aberto quando mudou no disco, mantendo a vista.
- Popup STZ Labs: lista com rolagem, cards recolhíveis (+N), contribuições com versão; Harlem nos créditos.

## Lançado na 0.6.0 (24/11/2026)

- **Exportar textos (.zip)** (Projeto → Exportar textos): `data/Translate/*.ini` editados, aplicados sobre a versão atual do jogo, para levar a outro PC.
- **Receber versões beta** (Ajuda): desligado por padrão; ao marcar, verifica na hora. Atualizador entende `X.Y.Z-beta.N`.
- **Manifesto remoto** (`app-manifest.json` no `main`): avisos, versão mínima e funções desligáveis sem lançar versão ([como usar](release.md#manifesto-remoto-avisos-sem-lançar-versão)).

## Já existia (0.5.4)

- Projetos de UI com envio ao jogo (F5), exportação da UI em .zip para o launcher, histórico em `.history/`.
- Comparação com a UI oficial (`GameDataFileList.txt` + cache `.official-ui`), controles novos de atualizações.
- Edição de textos de `data/Translate` guardada no `project.db` e reaplicada ao enviar.
- Atualizador pelo GitHub Releases (`releases/latest`, só estáveis).
