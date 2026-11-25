# Decisões

Log curto: uma linha por decisão. Detalhes ficam na nota indicada.

| ID | Data | Decisão | Onde vale |
|---|---|---|---|
| D01 | 24/11/2026 | Barra lateral continua à esquerda; resolver o pulo automático de aba e adicionar Ctrl+1..4 em vez de voltar às abas no topo | [roadmap](roadmap.md#fase-1--ajustes-rápidos-070-beta1) |
| D02 | 24/11/2026 | Canal beta pelo caminho A: a opção "Receber versões beta" chega numa estável (0.6.0); as betas começam na versão seguinte | [beta](beta.md) |
| D03 | 24/11/2026 | Exportar textos entra na 0.6.0 (Fase 0) | [estado atual](status.md) |
| D04 | 24/11/2026 | Testes da Fase 1 feitos pelo mantenedor antes do lançamento | [roadmap](roadmap.md) |
| D05 | 24/11/2026 | **Em aberto:** migrar a interface para pywebview + Vite + React + Tailwind v4, mantendo o núcleo Python; Tauri descartado (Rust). Decidir depois de um protótipo | [migração web](migracao-web.md) |
| D06 | 24/11/2026 | Fase 0 (0.6.0 estável): Exportar textos + opção de beta; a Fase 1 vira 0.7.0 e é a primeira a passar por beta | [roadmap](roadmap.md#fase-0--base-do-canal-beta-060) |
| D07 | 24/11/2026 | Pre-releases (betas) não vão para o Discord nem para o site; só estáveis | [release](release.md) |
| D08 | 24/11/2026 | Manifesto remoto no GitHub (`app-manifest.json`, branch main), não no site: edita com commit, tem histórico, não depende de deploy e o GitHub já é contatado pelo atualizador | [release](release.md#manifesto-remoto-avisos-sem-lançar-versão) |
| D09 | 24/11/2026 | Fase 2 resolve o fluxo "edita na mão" levando a edição para o projeto (Notepad++ no botão direito + Ctrl+R + F5), em vez de abrir a pasta do jogo sem projeto; "Abrir pasta sem projeto" vai para Depois | [roadmap](roadmap.md#fase-2--projetos-070-beta2-em-diante) |
| D10 | 25/11/2026 | O launcher aplica uma UI copiando os arquivos dela por cima da pasta UI (teste medido). Uma UI = os arquivos que ela contém; o editor envia e exporta só o que difere do oficial (CRC do GameDataFileList.txt), o que também tira `map` e ícones sem regra especial | [launcher](launcher.md) |
| D11 | 25/11/2026 | Checkpoint de projeto = .zip só com o que difere do oficial (poucos MB), não *hard links*: com hard links, editar no Notepad++ (que salva por cima) mudaria os dois projetos | [roadmap](roadmap.md#fase-2--projetos-070-beta2-em-diante) |
| D12 | 25/11/2026 | O roadmap inteiro (Fases 1–3) é a 0.7.0: cada fase sai como `0.7.0-beta.N` para quem sugeriu testar, e só no fim sai a 0.7.0 estável. Evita encher de releases estáveis feitas só para teste (como acontecia com o Rosthy) | [roadmap](roadmap.md), [beta](beta.md) |
