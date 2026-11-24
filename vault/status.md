# Estado atual

Revisão: **24/11/2026**. Última release publicada: **0.5.4**.

## Pronto, ainda não lançado

- **Exportar textos (.zip)** (Projeto → Exportar textos): gera `data/Translate/*.ini` só dos arquivos que o projeto edita, com as edições aplicadas sobre a versão atual do jogo. Serve para levar os textos a outro PC (ex.: uma VM) sem o editor. Testes e traduções en/es/fr prontos; **não commitado**. Entra na 0.6.0 ([Fase 0](roadmap.md#fase-0--base-do-canal-beta-060)).

- **Receber versões beta** (Ajuda): opção desligada por padrão; ao marcar, verifica na hora. O atualizador entende `X.Y.Z-beta.N` e, com a opção, consulta também as pre-releases. Testes e traduções prontos; **não commitado**. Entra na 0.6.0.

- **Manifesto remoto:** avisos, versão mínima e funções desligáveis via `app-manifest.json`. Testes e traduções prontos; **não commitado**. Entra na 0.6.0.

## Funciona hoje (0.5.4)

- Projetos de UI com envio ao jogo (F5), exportação da UI em .zip para o launcher, histórico em `.history/`.
- Comparação com a UI oficial (`GameDataFileList.txt` + cache `.official-ui`), controles novos de atualizações.
- Edição de textos de `data/Translate` guardada no `project.db` e reaplicada ao enviar.
- Atualizador pelo GitHub Releases (`releases/latest`, só estáveis).
