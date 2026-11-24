# Estado atual

Revisão: **24/11/2026**. Última release publicada: **0.6.0** (24/11/2026).

## Lançado na 0.6.0 (24/11/2026)

- **Exportar textos (.zip)** (Projeto → Exportar textos): `data/Translate/*.ini` editados, aplicados sobre a versão atual do jogo, para levar a outro PC.
- **Receber versões beta** (Ajuda): desligado por padrão; ao marcar, verifica na hora. Atualizador entende `X.Y.Z-beta.N`.
- **Manifesto remoto** (`app-manifest.json` no `main`): avisos, versão mínima e funções desligáveis sem lançar versão ([como usar](release.md#manifesto-remoto-avisos-sem-lançar-versão)).

## Já existia (0.5.4)

- Projetos de UI com envio ao jogo (F5), exportação da UI em .zip para o launcher, histórico em `.history/`.
- Comparação com a UI oficial (`GameDataFileList.txt` + cache `.official-ui`), controles novos de atualizações.
- Edição de textos de `data/Translate` guardada no `project.db` e reaplicada ao enviar.
- Atualizador pelo GitHub Releases (`releases/latest`, só estáveis).
