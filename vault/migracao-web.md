# Migração da interface para web (em estudo)

Revisão: **24/11/2026**. Status: **ideia em estudo, nada decidido** ([D05](decisions.md)). Não entra antes das fases do [roadmap](roadmap.md) sem decisão explícita.

## Por que pensar nisso

- O Qt Widgets limita o visual: o QSS não tem transições, sombra e desfoque são caros, o layout é rígido e os componentes nativos (menus, rolagem, diálogos) aparecem por baixo do tema. Polir ajuda, mas a "cara de programa Python dark" continua.
- Interface personalizável (painéis arrastáveis, reordenar com animação) é bem mais barata na web (dnd-kit, dockview, Framer Motion, Tailwind).
- Um editor de XML completo vem pronto na web (Monaco ou CodeMirror 6), o que ajuda na ideia de o editor bastar sem Notepad++ ([roadmap](roadmap.md#depois)).
- O instalador tende a **diminuir**: hoje são 130 MB instalados, dos quais **92 MB são do Qt** (PySide6); o instalador tem 41 MB.

## Stack proposto

| Parte | Escolha |
|---|---|
| Janela | **pywebview** com Edge WebView2 (já vem no Windows 10/11), sem embutir navegador |
| Frontend | **Vite + React + Tailwind v4** (+ TypeScript) |
| Backend | **O Python que já existe**: XML Big5, DDS, `.ini`, SQLite, launcher, publicar, atualizador |
| Ponte | `js_api` do pywebview (front → Python) e `evaluate_js` (Python → front: progresso, arquivo mudou) |
| Empacotamento | PyInstaller + Inno Setup, como hoje |

Vite não é alternativa ao Rust: ele é a ferramenta de build do frontend e serve tanto ao pywebview quanto ao Tauri. A escolha real é **quem hospeda a janela**:
- **pywebview (Python):** sem Rust, núcleo intacto, hot reload do Vite no front e reiniciar em 1 s no Python.
- **Tauri (Rust):** compilação lenta a cada teste, e o núcleo Python teria que ir como processo à parte (sidecar) ou ser reescrito.
- **Descartados:** Electron (embute Chromium, +150 MB), QtWebEngine híbrido (mantém o Qt e soma ~100 MB), servidor local + navegador (cara de site), Wails (mais uma linguagem), Flet/NiceGUI (pouca liberdade visual).

**Referência pronta:** o `stz-suite` já fez essa migração (PySide6/QML → pywebview + React + Tailwind 4). Ver `stz-suite/plano-migracao-webview.md`, `docs/ARCHITECTURE.md` e `stz_suite/ui_web_shell/web_app.py`.

## O que é fácil e o que dá trabalho

### DDS: fácil
Das 85 DDS da pasta `UI` do jogo, 75 são RGB 32 bits sem compressão (cabeçalho de 128 bytes + pixels BGRA), 8 são DXT1 e 2 são ARGB4444. O navegador só não abre `.dds` em `<img>`; não há nada difícil no formato. O editor só **lê** DDS (o atlas muda o XML, não a imagem).

- O front lê os bytes brutos direto do disco (`file://` ou mapeamento de pasta do WebView2) e decodifica num **Web Worker**. São ~100–200 linhas de TypeScript.
- 32/16 bits viram textura WebGL direto; DXT1 pode ir comprimido para a GPU (`WEBGL_compressed_texture_s3tc`, suportado no Edge).
- **Nunca** passar imagem pela ponte (base64 de 16 MB trava). Pela ponte só vão comandos e dados pequenos.
- O Python continua vigiando a pasta e só avisa "textura X mudou".

### Canvas: reescrita moderada, não difícil
Canvas + atlas somam ~3,2 mil linhas hoje, mas as regras do jogo ficam no Python (largura/altura trocadas, ordem dos UVs, estados de botão, posição na tela em `game_layout.py`, textos dos controles). O front só desenha e devolve "elemento 5 foi para x,y".

| Comportamento | Pronto na web |
|---|---|
| Selecionar, arrastar, alças de redimensionar, seleção múltipla | **Konva / react-konva** (`Transformer`) |
| Zoom e pan | Escala do palco no Konva (ou PixiJS + pixi-viewport) |
| Camadas, camadas de referência | Camadas do Konva |
| Travar eixo, encaixar em pixel inteiro | `dragBoundFunc` |
| Atlas (recorte do DDS) | Imagem + retângulo arrastável (mesma lib) |
| Preview do jogo | Fundo + posições calculadas pelo Python |
| Desfazer/refazer | Store central (Zustand) com pilha de undo |

O trabalho real são os **muitos detalhes de comportamento** acumulados (redimensionar grupo, Shift mantém proporção, prioridade da alça sobre painel sobreposto, texto com a fonte do jogo…) e a validação.

## Pontos de atenção

- **WebView2 ausente (Windows "lite": Tiny11, AtlasOS, ReviOS):** sem ele o pywebview cai no motor do IE e a janela abre em branco. O instalador precisa checar o registro e rodar o bootstrapper oficial (~2 MB). O app também deve checar ao abrir e oferecer a instalação. O instalador offline (~170 MB) fica só como download à parte.
- **Windows 7/8.1:** a versão atual **já não roda** (Python 3.12 e Qt 6 não suportam). Na web, o WebView2 parou na 109 e o Tailwind v4 exige Chrome 111+. Fora do escopo.
- **Servidor HTTP do pywebview:** não usar no Windows; o Bottle embutido trava a janela (aprendizado do stz-suite). Carregar o build do Vite por `file://`.
- **Configurações do usuário:** hoje ficam no Registro via `QSettings("Local", "GF UI Editor")`. Precisa de uma migração única (idioma, último projeto, navegação, confirmações, recentes).
- **Traduções:** os catálogos Qt (`.ts` en/es/fr, ~614 textos) precisam virar JSON (ex.: i18next). Dá para converter por script; manter a regra de todo texto novo sair traduzido.
- **`app.py` mistura interface e lógica** (~6,3 mil linhas). Antes de migrar, extrair a lógica para serviços Python sem Qt. **Vale a pena mesmo se a migração nunca acontecer:** testes mais simples e menos acoplamento.
- **Listas enormes:** com ícones incluídos são ~18 mil arquivos. Usar lista virtualizada (TanStack Virtual).
- **Comportamentos de navegador a desligar:** menu do botão direito padrão, zoom com Ctrl+roda da página, Ctrl+R/F5 recarregando, seleção de texto na interface, DevTools fora do modo dev.
- **Arrastar arquivos do Explorer para a janela:** conferir o suporte do pywebview a caminhos completos no drop.
- **Atalhos:** todos os atuais (F5, Ctrl+S, Ctrl+Z, I, setas, Ctrl+1..4 da Fase 1) precisam de equivalente e de teste.
- **Instância única e "Abrir com":** abrir um `.xml` pelo Explorer com o editor já aberto deve ir para a janela existente.
- **Atualizador:** continua em Python; só a janela de atualização vira tela web.
- **Desempenho do canvas** com UIs grandes e muitas texturas: medir cedo, no protótipo.

## Convivência das duas interfaces (toggle clássica/nova)

Viável, no mesmo modelo do `STZ-XML-Translator` (núcleo único em `core/app_controller.py`, `ui_mode` "classic"/"modern" no config).

- **Como:** um só executável. Configuração "Interface: clássica / nova (beta)", aplicada **ao reiniciar**. Qt e pywebview têm cada um o seu laço de janela; trocar ao vivo, ou misturar telas das duas na mesma janela, não vale o esforço.
- **Fallback automático:** sem WebView2 (Windows lite), o editor abre a clássica e avisa, em vez de abrir em branco. Atalho de linha de comando (`--ui classic`) para quando a nova não abrir.
- **Condição:** a etapa 0 (lógica fora do `app.py`, em serviços Python). As duas interfaces chamam os mesmos serviços, então projeto, `project.db`, `.history` e textos são os mesmos e dá para alternar no meio do trabalho.
- **Configurações compartilhadas:** sair do `QSettings` cedo para um arquivo/banco que as duas leem; senão cada interface fica com preferências diferentes.

**Peso:**
| Custo | Tamanho |
|---|---|
| Instalador | Sem ganho enquanto convivem: Qt (92 MB) + pywebview e build web (poucos MB) |
| Funcionalidade nova | **A clássica congela** (só correções); novidades só na nova. Sem essa regra, tudo é feito duas vezes |
| Testes | As duas suítes rodam até a remoção; o núcleo é um só |
| Manutenção | Duas telas para cada correção de interface; por isso a convivência tem prazo |

**Prazo sugerido:** a clássica sai na versão seguinte à promoção da nova a estável (etapa 14), depois de uma versão estável inteira com ela como fallback.

## Testes como checklist de migração

Hoje há 168 testes: **~67 do núcleo** (seguem valendo sem mudança) e **~101 de interface**, cujos nomes já descrevem comportamento (`test_shift_resize_preserves_original_aspect_ratio`, `test_ctrl_selection_moves_multiple_items_as_one_undo_step`…). Cada um vira um item do checklist da tela correspondente.

Por tela migrada:
1. **Núcleo (pytest):** regras do jogo intactas.
2. **Comportamento (Playwright):** clicar, arrastar com Shift, Ctrl+Z, digitar; um teste novo para cada teste antigo de interface.
3. **Mesma entrada, mesma saída (a mais forte):** mesmo XML real + mesma sequência de ações no editor antigo e no novo → comparar os **bytes** do XML gerado. Idem para `.ini`, `.zip` exportado e o que "Enviar para o jogo" grava.
4. **Desenho do canvas:** mesmo XML renderizado nos dois editores, comparação de pixels com tolerância. Depois, capturas de referência do Playwright para regressões futuras.

**Manual:** sensação (arrastar suave, zoom sem engasgo), se ficou bonito e uso real com UIs grandes e o jogo aberto.

Regra: uma tela só é dada como migrada quando todo o checklist dela tem teste novo passando.

## Ordem de implementação

0. **Preparar no editor atual (útil de qualquer jeito)**
   - Extrair de `app.py` a lógica para serviços Python sem Qt.
   - Criar o harness "mesma entrada, mesma saída" e gravar as saídas de referência com o editor Qt.
   - Listar o checklist por tela a partir dos testes de interface.
1. **Protótipo (ponto de decisão):** janela pywebview + ponte + leitura de DDS no Worker + canvas Konva **só leitura** de um XML real (ex.: BasicChar.xml). Medir desempenho, tamanho do instalador e sensação. **Só seguir se convencer.**
2. **Casca:** layout geral, tema (tokens Tailwind), barra lateral, atalhos, i18n, checagem do WebView2, instância única, **toggle clássica/nova** e configurações compartilhadas fora do `QSettings`.
3. **Tela inicial e projetos:** recentes, novo projeto, abrir, gerenciar/excluir (se a [Fase 2](roadmap.md#fase-2--projetos) ainda não tiver vindo).
4. **Lista de Arquivos XML e Texturas** (virtualizada, seções, filtros, camadas).
5. **Canvas só leitura** completo: zoom, pan, enquadrar, contornos, identificadores, preview do jogo, camadas de referência.
6. **Canvas editável:** selecionar, mover, redimensionar, grupo, eixo, undo/redo, salvar com diff.
7. **Painel de propriedades** (posição, textura, identificação, aparência, fonte).
8. **Atlas DDS** (recorte, estados de botão, thumbs).
9. **Textos** (busca, edição, importar, exportar).
10. **Publicar, exportar UI, UI oficial, resolver erro do jogo, histórico/restaurar.**
11. **Configurações e atualizador** (com migração do QSettings).
12. **Empacotamento:** PyInstaller sem Qt, Inno Setup com WebView2, conferir tamanho.
13. **Beta:** distribuir pelo [canal beta](beta.md) com o toggle; a clássica continua como padrão na estável.
14. **Promover a estável:** a nova vira padrão, a clássica fica como fallback por mais uma versão.
15. **Remover a clássica e o Qt** das dependências.

Durante a migração, a interface clássica recebe só correções pequenas; funcionalidade nova entra só na nova (ver [convivência](#convivência-das-duas-interfaces-toggle-clássicanova)).
