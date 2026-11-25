# Estado atual

Revisão: **25/11/2026**. Última release publicada: **0.7.0** (25/11/2026).

## 0.7.0 estável publicada (25/11/2026)
- Reúne as betas 1–3 (Fases 1, 2 e 3) mais as correções finais, sem beta.4: `map` fora dos projetos novos, Limpar remove mapas iguais ao oficial, textos do F5/criação, tamanho na tela inicial recalculado após Limpar/Puxar/Salvar versão.
- Notas consolidadas nos 4 idiomas; as betas ficam no `history` (estável para estável não as mostra).
- Instalador: `GF-UI-Editor-Setup-0.7.0.exe` (e `GF-UI-Editor-Setup.exe`), SHA-256 `391E045E35EFBF2EF3279691411D1CCFAA60F8224EBFCD0C50AE571A25894757`.
- Webhook "published" entregue (200) → card no #patch-notes.


## Beta 0.7.0-beta.3 publicada (25/11/2026, pre-release; Fase 3)
- Fonte no painel (cor, contorno, alinhamento, tamanho); seções da lista com rolagem própria e ordem ajustável.
- Roda do mouse não muda campos do painel; mãozinha nos diálogos e listas suspensas.
- Notas: estável para estável não mostra as betas (`release_notes.since`).
- Instalador: `GF-UI-Editor-Setup-0.7.0-beta.3.exe`, SHA-256 `0B223CCB761A5A7190F770A9F0A26963AAB866F73D075CD60DD320356A6DC549`.

## Beta 0.7.0-beta.2 publicada (25/11/2026, pre-release; Fase 2)
- Tela inicial completa; gerenciar projetos (duplicar, renomear, excluir com a cópia no jogo, seleção múltipla).
- Versões do projeto (checkpoints .zip só com o que difere do oficial).
- Puxar da pasta do jogo + proteção no F5 (cópia no .history dos arquivos editados fora, aviso com "Ver").
- Limpar projeto (histórico, ícones não editados, sobras do UICustom).
- Envio e .zip só com o que difere do oficial; contador no Enviar; Enviar ao salvar; Abrir no Notepad++.
- Instalador: `GF-UI-Editor-Setup-0.7.0-beta.2.exe`, SHA-256 `2844B7553BBDD1D0E6FA181C99DF93E7C616AB06E5216092D13C3BABF71D3E85`.

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
