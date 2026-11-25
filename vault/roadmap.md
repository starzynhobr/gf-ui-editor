# Roadmap

Revisão: **25/11/2026**. Cada fase vira uma **beta** da mesma versão; a estável só sai no fim do roadmap ([D12](decisions.md)). Origem dos itens: [feedback de 24/11/2026](feedback/2026-11-24-discord.md) e conversas de planejamento. Andamento: [quadro](backlog.md).

## Fase 0 — base do canal beta (0.6.0)

Estável. Leva o que já está pronto e prepara o canal beta, para que as betas comecem na versão seguinte ([D06](decisions.md)).

- [x] **Exportar textos (.zip)** (pronto, ainda não lançado; [estado atual](status.md)).
- [x] **"Receber versões beta"** em Ajuda: ao marcar, já verifica se há versão pendente, como "Verificar atualizações…" ([plano](beta.md)).
- [x] **Comparador de versões que entende `-beta.N`** e consulta à lista de releases quando a opção está ligada.
- [x] **Passo a passo de release documentado** ([release](release.md)).
- [x] **Manifesto remoto** (`app-manifest.json` no `main`): avisos, versão mínima e desligar funções sem lançar versão ([como usar](release.md#manifesto-remoto-avisos-sem-lançar-versão), [D08](decisions.md)).
- [x] Build, instalador e release 0.6.0 no GitHub (publicada em 24/11/2026; hook do site entregou ao Discord).

## Fase 1 — ajustes rápidos (0.7.0-beta.1)

`0.7.0-beta.1` publicada em 24/11/2026 (inclui também Ctrl+R recarregando o XML editado fora).

- [x] **Resetar zoom:** clicar na porcentagem (ex.: "236%") volta a 100%; atalho `Ctrl+0`. Hoje há −, + e Enquadrar.
- [x] **Navegar entre XMLs sem trocar de aba:** clique simples e setas ↑↓ abrem o XML no canvas e ficam em Arquivos XML; duplo clique ou Enter vão para Elementos. Hoje o clique pula sempre para Elementos (`side_tabs.setCurrentIndex(1)` em `app.py`).
- [x] **Atalhos das seções:** `Ctrl+1` Arquivos XML, `Ctrl+2` Texturas, `Ctrl+3` Elementos, `Ctrl+4` Textos, com o atalho no tooltip de cada ícone da barra lateral ([D01](decisions.md)).
- [x] **Botão Home** no canto superior esquerdo, antes do seletor de projeto. A ação "Tela inicial" já existe no menu ⚙ → Arquivo, mas só funciona com um XML aberto.
- [x] **"Abrir com" no Explorer:** o instalador registra o editor na lista "Abrir com" dos `.xml` (HKCU, sem admin, sem virar o programa padrão e removido ao desinstalar). Abrir pelo argumento já funciona hoje: só o XML, sem projeto, em ~0,4 s (NPCTalk.xml, 120 elementos). Opcional: item direto "Abrir no STZ GF UI" no menu clássico (no Windows 11 fica em "Mostrar mais opções").

## Fase 2 — projetos (0.7.0-beta.2 em diante)

Foco: o projeto como espaço de trabalho, inclusive para quem edita XML na mão. Revisado em 24/11/2026 depois do feedback do Harlem: ele edita na pasta do jogo e cria um projeto novo a cada conferência ([feedback](feedback/2026-11-24-discord.md)). A solução é tornar fácil editar **no projeto** (pelo editor ou no Notepad++), e não adaptar o editor a editar na pasta do jogo ([D09](decisions.md)).

- [x] **Tela inicial completa** (validada em 25/11/2026, sem commit; [esboço](#esboço-da-tela-inicial)): ocupa a janela toda (esconde a lista de arquivos e as propriedades); card "Continuar de onde parou" com o projeto atual (último XML, alterados, para onde envia, quando foi editado); ações rápidas Novo projeto, Abrir projeto e XML solto; lista de projetos com arquivos, tamanho em disco, data e filtro; coluna da direita com aviso do manifesto, novidades da versão e "como funciona" (3 passos + vídeo).
- [x] **Gerenciar projetos** (na lista da tela inicial): menu ⋯ com Abrir, Abrir pasta, Duplicar, Renomear e Excluir (Lixeira, com confirmação); modo Gerenciar com seleção múltipla. "Remover da lista" saiu: a lista é a própria pasta de projetos, então remover sem excluir não teria efeito duradouro.
  - **Excluir também a cópia no jogo:** cada projeto enviado com F5 tem a sua pasta `UICustom/<nome>`. Ao excluir o projeto, oferecer apagar essa pasta junto (só se nenhum outro projeto publica nela).
  - **Duplicar** = cópia completa normal (dois projetos para trabalhar em paralelo).
- [x] **Versões do projeto (checkpoint)** (validada em 25/11/2026, sem commit): "Salvar versão" guarda um .zip só com os arquivos que diferem do oficial + as configurações do projeto (o STZ-UI inteiro cabe em ~6,5 MB); "Restaurar versão" / "Criar projeto a partir desta versão" recria o projeto aplicando o .zip sobre o oficial (a mesma regra do launcher, [D10](decisions.md)). Substitui a ideia de *hard links*, descartada porque programas que salvam por cima do arquivo (Notepad++, editores de imagem) mudariam os dois projetos juntos ([D11](decisions.md)).
- [x] **Puxar arquivos da pasta do jogo para o projeto** (validado em 25/11/2026, com a proteção abaixo; Projeto → Puxar da pasta do jogo, botão no card Continuar e no ⋯; a lista diz de onde veio cada arquivo: editado fora, de outra UI, enviado pelo editor ou oficial): compara a pasta `UI` do jogo (ou uma UI do UICustom) com o projeto e mostra a lista de arquivos diferentes para escolher; nada é trocado sem a pessoa marcar, e o que for substituído no projeto vai para `.history`. Não é só para usar uma vez: a proteção abaixo o oferece sempre que fizer falta.
  - **Proteção no F5, sem atrito** (implementada: registro em `<pasta de projetos>/.sent-to-game.json`, por pasta do jogo e comum a todos os projetos; cópias no `.history` com sufixo `-jogo`; arquivos iguais a uma UI de UICustom não contam como editados fora; sem lista oficial nem registro, não acusa): o F5 nunca pergunta nem bloqueia; continua só enviando. O editor guarda o CRC de cada arquivo que enviou; se um arquivo da pasta `UI` estiver diferente do que ele mandou (editado fora), guarda uma cópia dele antes de sobrescrever (no `.history` do projeto) e, depois de enviar, mostra um aviso discreto: "2 arquivos da pasta do jogo tinham sido editados fora e foram substituídos; cópia guardada · Ver". O Puxar continua sendo uma ação separada, que a pessoa chama quando quiser; abre com nada marcado.
- [x] **"Abrir no Notepad++" / editor de texto** (sem Notepad++, usa o Bloco de Notas) no botão direito de cada XML da lista, abrindo a cópia **do projeto**. Com o Ctrl+R (0.7.0) quem edita na mão passa a editar no lugar certo. Avaliar recarregar sozinho quando o XML mudar no disco, como já acontece com o .dds.
- [x] **UI enviada = só o que difere do oficial** (validada em 25/11/2026, sem commit) ([teste do launcher](launcher.md), [D10](decisions.md)): F5 (`UICustom/<nome>`) e "Exportar .zip" levam só os arquivos cujo CRC difere do `GameDataFileList.txt`. `map`, ícones e tudo que ninguém mexeu ficam de fora sozinhos (o `map` sozinho são 163 MB por projeto e por UI). A cópia para a pasta `UI` já é incremental (só o que difere do que está lá) e continua igual.
- [x] **Deixar claro que Ctrl+S não envia ao jogo** (o Harlem salvou e esperou ver no jogo): contador no botão "Enviar para o jogo" quando há algo salvo e não enviado ("Enviar para o jogo · 3"), e opção "Enviar para o jogo ao salvar" (desligada por padrão) para quem quer ver no jogo a cada ajuste.
- [x] **Limpar projeto** (validado em 25/11/2026; Projeto → Limpar projeto… e ⋯ → Limpar…). Ficou de fora tirar do projeto os arquivos iguais ao oficial e o `map`: o editor lê as texturas só da pasta `ui/` do projeto e o F5 deixa a pasta UI do jogo igual a ela, então o projeto tem de continuar completo. O que sai: backups do `.history` (com mais de 30 dias ou todos; os `original.*` ficam), ícones do jogo iguais ao oficial (desliga "incluir ícones" quando não sobra nenhum editado), sobras de `UICustom/<nome>` (só a pasta própria) e temporários. Medido em cópias: STZ-UI 524 → 414 MB (histórico 110 MB); UI-HERO tinha 45 MB sobrando no UICustom. Plano original (o Harlem chegou a **10 GB** de projetos: ~35 cópias de 240–500 MB; com ícones marcados, ~1 GB cada): remover pastas inteiras (`map`, ícones), arquivos idênticos ao oficial e backups antigos do `.history`. Também dá para desfazer a escolha "incluir ícones" feita na criação.
  - Medido no STZ-UI: `ui/map` tem 291 dos 705 arquivos (163 de 382 MB); `.history` tem 111 MB.
  - Com a regra "só o que difere do oficial", o projeto pode continuar tendo o `map` (o editor desenha com ele); quem pesa é a cópia enviada ao jogo e o .zip.

### Esboço da tela inicial

```
┌ ⌂ Tela inicial ─────────────────────────────────────── STZ Labs ⚙ ┐
│ ┌ CONTINUAR DE ONDE PAROU ─────────────────┐  ┌ AVISO ───────────┐ │
│ │ STZ-UI · Channel.xml · 10 alterados       │  │ (manifesto)      │ │
│ │ envia para UICustom/STZ-UI · há 5 min     │  ├ NOVIDADES ───────┤ │
│ │ [Continuar →] [Puxar do jogo] [Duplicar]  │  │ • 3 itens        │ │
│ │ [Abrir pasta]                              │  │ Ver todas        │ │
│ └───────────────────────────────────────────┘  ├ COMO FUNCIONA ───┤ │
│ [Novo projeto] [Abrir projeto] [XML solto]     │ 1 cópia segura   │ │
│ ┌ PROJETOS · 6        [filtrar] [Gerenciar] ┐  │ 2 edite aqui     │ │
│ │ Nome  Arquivos  Tamanho  Editado      ⋯   │  │ 3 F5 envia       │ │
│ └───────────────────────────────────────────┘  └──────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
```

## Fase 3 — edição (betas seguintes da 0.7.0)

- [x] **Fonte no painel do elemento** (validada em 25/11/2026): em Aparência, Cor do texto (seletor de cor, grava BGR), Contorno, Alinhamento e Tamanho, cada campo só quando o controle tem o atributo; desfazer funciona e o texto do canvas muda na hora. `FontStyle=1` é **contorno preto**, não negrito (o preview já desenhava assim); o preview usa sempre Arial 8 do cliente, então o tamanho só aparece no jogo. A roda do mouse sobre listas suspensas e campos numéricos do painel rola o painel em vez de mudar o valor (pedido do usuário em 25/11/2026). Plano original: editar cor, negrito, alinhamento e tamanho. Hoje só aparece como texto ("cor 65535 · estilo 1"), sem edição. Levantamento nos 365 XMLs oficiais:

  | Atributo | Onde fica | Valores |
  |---|---|---|
  | `FontColor` | BaseCtrlProperty (11.241×) | número da cor: 16777215 branco, 65535 amarelo, 0 preto |
  | `FontStyle` | BaseCtrlProperty (11.241×) | 0 normal, 1 negrito |
  | `TextAlign` | TextNode (6.565×) | 0 esquerda, 1 centro, 2 direita |
  | `FontSize` | TextNode (6.305×) | 9 e 10 na maioria |

  Mostrar os campos só quando o controle tem o atributo; conferir a ordem dos canais de cor (65535 = amarelo indica BGR).
- [x] **Seções com rolagem própria na lista de XMLs** (validada em 25/11/2026; uma árvore por seção num divisor vertical, alturas em `files_section_heights` no QSettings; seção sem arquivos some, também com o filtro; dá para **mudar a ordem** arrastando o título ou pelo botão direito — Mover para cima/baixo, Restaurar ordem padrão —, salva em `files_section_order`) (estilo NifSkope): "Camadas" numa caixa de altura ajustável com rolagem própria, "Todos" com outra; divisor arrastável que lembra a altura. Hoje é uma árvore só e as camadas empurram o resto para baixo.

## Correções finais (entraram direto na 0.7.0, sem beta.4)

- [x] **`map` fora dos projetos novos** (validado, 0.7.0): nenhum XML aponta para os `map/*.dds` (conferido nos XMLs da UI do jogo) e o editor só lê texturas da raiz de `ui/`; a afirmação anterior de que "o editor desenha com o map" estava errada. A criação deixa a pasta `map` de fora (menos ~163 MB por projeto, salvo com "incluir ícones"); projetos antigos continuam listando o que têm, e **Limpar projeto** ganhou "Mapas do jogo iguais ao oficial" (mapas editados ficam).
- [x] **Textos do F5 e da criação** (validado, 0.7.0): a barra do F5 dizia "Publicando no jogo… 653/704" e parecia enviar tudo; agora "Conferindo o que mudou e enviando para o jogo…", e no fim "Nada mudou: a pasta UI do jogo já está igual ao projeto" ou "N arquivo(s) enviados". A criação avisa que para o jogo só vai o que for alterado.

## Depois

- [ ] **Projetos leves (UI base como fonte da verdade)** — ideia de 25/11/2026: o projeto guarda só os arquivos alterados e o resto vem de uma UI base guardada uma vez por CRC; ao salvar um arquivo ainda não alterado, ele é copiado para o projeto (cópia na escrita). O modelo é o mesmo do launcher e das versões (.zip só com o que difere do oficial). Peças que já existem: lista oficial com CRC, cache `.official-ui` por CRC, `shipped_files`, formato das versões. Trabalho grande: `project.ui_dir / arquivo` aparece em muitos lugares, as texturas precisam de busca em camadas, e Notepad++ / editor de imagem precisam de arquivo real (copiar antes de abrir). Candidato a 0.8.0, com uma conversão dos projetos atuais.

- [ ] **Aviso de atualização dos textos do jogo:** detectar pelo CRC do `GameDataFileListT.txt` que o launcher trocou os `.ini`; mostrar IDs novos, textos oficiais alterados e edições do projeto desfeitas (com "Reenviar edições"); comparar ignorando CRLF/LF.
- [ ] **Abrir pasta sem projeto** (antes "Verificar pasta"): o modo XML solto com escolha de pasta e as checagens da UI oficial. Saiu da Fase 2: trataria o sintoma (editar na pasta do jogo); fica para se alguém ainda precisar.
- [ ] **Ver o código do XML:** aba ou painel só leitura com o texto do XML (estado atual, com as edições ainda não salvas), cores de sintaxe, números de linha, Ctrl+F e sincronia com o canvas (clicar num elemento leva à linha dele e vice-versa). Edição direta do texto fica para depois: exige validar, reconverter para Big5 e conviver com o desfazer.
- [ ] **Estudo da migração da interface para web** (pywebview + Vite + React + Tailwind v4): preparação no editor atual e protótipo como ponto de decisão ([plano](migracao-web.md), [D05](decisions.md)).
- [ ] **Funções dormentes / liberação gradual** (quando surgir a primeira): `enabled_features` no manifesto para ligar remotamente uma função que já vem desligada, e porcentagem por instalação (número aleatório guardado no PC) para liberar a parte das pessoas. Entra junto com a versão que trouxer a função, não antes.
- [x] **Primeira beta:** `0.7.0-beta.1` (Fase 1), publicada em 24/11/2026 pelo canal beta da 0.6.0.

## Decidido não fazer agora

- Voltar a barra lateral para abas no topo ([D01](decisions.md)).
