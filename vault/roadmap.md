# Roadmap

Revisão: **24/11/2026**. Cada fase vira uma versão. Origem dos itens: [feedback de 24/11/2026](feedback/2026-11-24-discord.md) e conversas de planejamento. Andamento: [quadro](backlog.md).

## Fase 0 — base do canal beta (0.6.0)

Estável. Leva o que já está pronto e prepara o canal beta, para que as betas comecem na versão seguinte ([D06](decisions.md)).

- [x] **Exportar textos (.zip)** (pronto, ainda não lançado; [estado atual](status.md)).
- [x] **"Receber versões beta"** em Ajuda: ao marcar, já verifica se há versão pendente, como "Verificar atualizações…" ([plano](beta.md)).
- [x] **Comparador de versões que entende `-beta.N`** e consulta à lista de releases quando a opção está ligada.
- [x] **Passo a passo de release documentado** ([release](release.md)).
- [x] **Manifesto remoto** (`app-manifest.json` no `main`): avisos, versão mínima e desligar funções sem lançar versão ([como usar](release.md#manifesto-remoto-avisos-sem-lançar-versão), [D08](decisions.md)).
- [x] Build, instalador e release 0.6.0 no GitHub (publicada em 24/11/2026; hook do site entregou ao Discord).

## Fase 1 — ajustes rápidos (0.7.0)

Primeira a passar por beta (`0.7.0-beta.N`) antes da estável.

- [ ] **Resetar zoom:** clicar na porcentagem (ex.: "236%") volta a 100%; atalho `Ctrl+0`. Hoje há −, + e Enquadrar.
- [ ] **Navegar entre XMLs sem trocar de aba:** clique simples e setas ↑↓ abrem o XML no canvas e ficam em Arquivos XML; duplo clique ou Enter vão para Elementos. Hoje o clique pula sempre para Elementos (`side_tabs.setCurrentIndex(1)` em `app.py`).
- [ ] **Atalhos das seções:** `Ctrl+1` Arquivos XML, `Ctrl+2` Texturas, `Ctrl+3` Elementos, `Ctrl+4` Textos, com o atalho no tooltip de cada ícone da barra lateral ([D01](decisions.md)).
- [ ] **Botão Home** no canto superior esquerdo, antes do seletor de projeto. A ação "Tela inicial" já existe no menu ⚙ → Arquivo, mas só funciona com um XML aberto.
- [ ] **"Abrir com" no Explorer:** o instalador registra o editor na lista "Abrir com" dos `.xml` (HKCU, sem admin, sem virar o programa padrão e removido ao desinstalar). Abrir pelo argumento já funciona hoje: só o XML, sem projeto, em ~0,4 s (NPCTalk.xml, 120 elementos). Opcional: item direto "Abrir no STZ GF UI" no menu clássico (no Windows 11 fica em "Mostrar mais opções").

## Fase 2 — projetos

- [ ] **Gerenciar e excluir projetos:** botão direito nos Recentes ("Remover da lista", "Excluir projeto…" para a Lixeira, com confirmação) e uma tela "Gerenciar projetos" com tamanho, data e seleção múltipla.
- [ ] **Atualizar o projeto a partir da pasta do jogo ou de uma UI do UICustom:** o botão de atualizar pergunta a origem (projeto, `Grand Fantasia Violet\UI`, UICustom); lista os arquivos diferentes e novos para escolher; o que for substituído vai para `.history`. Evita criar um projeto novo cada vez que se quer puxar a UI de novo.
- [ ] **Limpar projeto:** remover pastas inteiras (`map`, ícones), arquivos idênticos ao oficial e backups antigos do `.history`. Também dá para desfazer a escolha "incluir ícones" feita na criação.
  - Medido no STZ-UI: `ui/map` tem 291 dos 705 arquivos (163 de 382 MB); `.history` tem 111 MB.
  - UIs de terceiros em UICustom levam 0 a 14 arquivos de `map`: o launcher completa com o oficial.
  - Considerar `map` desmarcado por padrão ao criar o projeto (hoje entra sempre; não está em `GAME_ASSET_FOLDERS`).

## Fase 3 — edição

- [ ] **Fonte no painel do elemento:** editar cor, negrito, alinhamento e tamanho. Hoje só aparece como texto ("cor 65535 · estilo 1"), sem edição. Levantamento nos 365 XMLs oficiais:

  | Atributo | Onde fica | Valores |
  |---|---|---|
  | `FontColor` | BaseCtrlProperty (11.241×) | número da cor: 16777215 branco, 65535 amarelo, 0 preto |
  | `FontStyle` | BaseCtrlProperty (11.241×) | 0 normal, 1 negrito |
  | `TextAlign` | TextNode (6.565×) | 0 esquerda, 1 centro, 2 direita |
  | `FontSize` | TextNode (6.305×) | 9 e 10 na maioria |

  Mostrar os campos só quando o controle tem o atributo; conferir a ordem dos canais de cor (65535 = amarelo indica BGR).
- [ ] **Seções com rolagem própria na lista de XMLs** (estilo NifSkope): "Camadas" numa caixa de altura ajustável com rolagem própria, "Todos" com outra; divisor arrastável que lembra a altura. Hoje é uma árvore só e as camadas empurram o resto para baixo.

## Depois

- [ ] **Aviso de atualização dos textos do jogo:** detectar pelo CRC do `GameDataFileListT.txt` que o launcher trocou os `.ini`; mostrar IDs novos, textos oficiais alterados e edições do projeto desfeitas (com "Reenviar edições"); comparar ignorando CRLF/LF.
- [ ] **Ver o código do XML:** aba ou painel só leitura com o texto do XML (estado atual, com as edições ainda não salvas), cores de sintaxe, números de linha, Ctrl+F e sincronia com o canvas (clicar num elemento leva à linha dele e vice-versa). Edição direta do texto fica para depois: exige validar, reconverter para Big5 e conviver com o desfazer.
- [ ] **Estudo da migração da interface para web** (pywebview + Vite + React + Tailwind v4): preparação no editor atual e protótipo como ponto de decisão ([plano](migracao-web.md), [D05](decisions.md)).
- [ ] **Funções dormentes / liberação gradual** (quando surgir a primeira): `enabled_features` no manifesto para ligar remotamente uma função que já vem desligada, e porcentagem por instalação (número aleatório guardado no PC) para liberar a parte das pessoas. Entra junto com a versão que trouxer a função, não antes.
- [ ] **Primeira beta:** `0.7.0-beta.1` (Fase 1), já pelo canal beta da 0.6.0.

## Decidido não fazer agora

- Voltar a barra lateral para abas no topo ([D01](decisions.md)).
