# Interface web: blocos e ponte

Revisão: **25/11/2026**. Decisão do usuário: **sem protótipo de medição**. A migração ([plano](migracao-web.md)) avança em blocos grandes, com dois agentes em paralelo, e a interface clássica (Qt) continua funcionando até a nova cobrir tudo.

## Como rodar

```powershell
cd web; npm install; npm run build; cd ..
.venv\Scripts\python.exe -m gf_ui_editor --ui web           # build em src/gf_ui_editor/web_dist
```
Com hot reload: `npm run dev` em `web/` e depois `python -m gf_ui_editor --ui web --dev`. Sem `--ui`, abre a clássica.

## Estrutura e donos

| Parte | Arquivos | Dono no bloco 1 |
|---|---|---|
| Janela e composição da ponte | `src/gf_ui_editor/web_shell.py` | principal (só compõe; não pôr lógica aqui) |
| Ponte: casca, tela inicial, projetos, lista de arquivos, preferências | `src/gf_ui_editor/web_api/projects.py` | **Claude 2** |
| Ponte: documento e canvas | `src/gf_ui_editor/web_api/canvas.py` | **Codex** |
| Casca do front (layout, barra, lateral, tela inicial, listas, i18n) | `web/src/` exceto `canvas/` | **Claude 2** |
| Canvas (DDS, Konva, zoom/pan, preview do jogo) | `web/src/canvas/` | **Codex** |
| Cliente da ponte | `web/src/bridge.ts` | os dois só **acrescentam** tipos/funções no fim |

A casca monta `<CanvasView path={xml aberto} />` (de `web/src/canvas/CanvasView.tsx`) no centro e não mexe no que há dentro. O canvas não mexe na casca. Mudança fora da sua área: pedir na resposta final, não fazer.

## Regras da ponte

- `WebApi` herda de `ProjectsApi` e `CanvasApi`. Método público = `window.pywebview.api.<nome>`; nomes em `snake_case`; devolvem só JSON (dict/list/str/int/float/bool/None). Erros: exceção Python (vira rejeição da Promise no front).
- **Sem lógica nova na ponte**: ela só chama os serviços sem Qt da etapa 0 (`project`, `file_list`, `home`, `publishing`, `preferences`, `text_preview`, `window_geometry`…). Se faltar um serviço, cria-se o serviço (com teste), não código na ponte.
- **Nada de imagem pela ponte.** O front lê os `.dds` do disco. Caminho recomendado: mapear a pasta da UI aberta num host virtual do WebView2 (`CoreWebView2.SetVirtualHostNameToFolderMapping`, via `window.native` no evento `shown`/`loaded`, como o stz-suite faz com o ícone) e o front faz `fetch("https://gfui-assets/<arquivo>.dds")`. A ponte só informa a URL base (`asset_base(...)`).
- Python → front: `self._emit("evento", dados)` (ex.: progresso, "arquivo mudou no disco").
- Preferências: `preferences.Preferences` com o mesmo armazenamento da clássica (as duas interfaces leem as mesmas preferências).
- Textos visíveis: i18n no front com os mesmos 4 idiomas (pt_BR, en_US, es_ES, fr_FR); os catálogos vêm dos `.ts` do Qt convertidos por script (`web/scripts/`), e texto novo sai traduzido nos 4.
- Comportamentos de navegador desligados: menu de contexto padrão, Ctrl+roda zoom da página, Ctrl+R/F5 recarregando, seleção de texto fora de campos.
- `WebApi._attach(window)` liga a janela e chama o preparo de cada área (`_attach_canvas_assets`…): scripts que montam a janela só chamam `_attach`.

## Testes da web

- Janelas de teste **sem foco e fora da tela**: `create_window(..., **window_options())` e capturas com `capture_window(hwnd, caminho)` (PrintWindow), de `harness/offscreen.py`. Nada pisca nem rouba o foco. `GF_HARNESS_VISIBLE=1` mostra a janela para depurar. A clássica já roda com `QT_QPA_PLATFORM=offscreen`.
- Caixa de areia: HOME/APPDATA trocados e QSettings desviado para INI (senão grava nas preferências reais).
- `harness/web_smoke.py <saida> <copia_do_jogo>`: tela inicial → novo projeto → abrir XML (canvas desenhado) → F5 → idioma → bloqueios do navegador.
- `harness/canvas_compare.py`: canvas da clássica × da web, pixel a pixel com tolerância.
- `harness/run.ps1`: a clássica tem que sair igual à referência.

## Bloco 1 (feito, 25/11/2026)

- **Claude 2 — casca e projetos:** layout geral (barra superior, lateral com Arquivos XML / Texturas / Elementos / Textos e Ctrl+1..4, barra de status), tema, i18n, tela inicial completa (continuar, projetos com filtro/tamanho/data, novo projeto, abrir, duplicar/renomear/excluir), lista de Arquivos XML e Texturas com as seções (camadas/alterados/todos, lista virtualizada), abrir um XML (passa o caminho ao `CanvasView`), F5 "Enviar para o jogo" e a escolha de interface (preferência `ui_mode` lida no `main` quando não há `--ui`; item nas configurações das duas interfaces, vale ao reiniciar).
- **Codex — canvas só leitura:** decodificador DDS em TypeScript num Web Worker (RGB 32 bits, DXT1, ARGB4444), acesso aos arquivos pela pasta mapeada, `CanvasView` com Konva: elementos com textura e recorte (UV), zoom, pan, enquadrar, contornos, preview do jogo (posições calculadas no Python: `game_layout`, deslocamentos de preview), modos de texto (via `text_preview`), seleção visual de um elemento (sem editar ainda).

## Bloco 2 (feito, 25/11/2026): edição

**Contrato compartilhado:** `web/src/doc/store.ts` (estado do XML aberto, seleção, edições com desfazer, salvar) e `src/gf_ui_editor/web_api/document.py` (documento em memória no Python, fonte da verdade). As assinaturas do `store.ts` não mudam sem combinar; quem implementa é o canvas.

| Parte | Arquivos | Dono |
|---|---|---|
| Documento em memória, edição, diff, salvar | `web_api/document.py`, serviços sem Qt | **Codex** |
| `doc/store.ts` (implementação) e canvas editável | `web/src/doc/`, `web/src/canvas/` | **Codex** |
| Árvore de elementos (Ctrl+3), painel de propriedades, salvar/descartar na casca, atalhos globais | `web/src/` fora de `canvas/` e `doc/`, `web_api/projects.py` | **Claude 2** |

- **Codex:** selecionar (clique, Ctrl, caixa), mover arrastando, alças de redimensionar, grupo, Shift mantém proporção, travar eixo, setas (1 px, Shift 10), encaixe em pixel inteiro, raiz que o jogo posiciona andando como a clássica (`window_geometry`), área fantasma, travados/escondidos/isolado respeitados no canvas, desfazer/refazer como lotes, salvar com backup e diff (`xml_document`), recarregar quando o XML muda no disco.
- **Claude 2:** árvore de elementos como a clássica (hierarquia, filtro via `text_preview.search_text`, esconder/travar/isolar, colunas), painel de propriedades (identificação, posição/tamanho editáveis com setas/roda desligada, textura, aparência/fonte com seletor de cor, campos só quando o controle tem o atributo), barra superior Salvar habilitado com o diff antes de gravar (como a clássica), "Descartar alterações?" ao trocar de XML/projeto/fechar, Ctrl+S/Ctrl+Z/Ctrl+Y/Ctrl+Shift+Z, F5 salvando antes.
- Verificado na junção: smoke da web 61/61 (editar, desfazer/refazer, salvar com diff, descartar), XML gravado pela web idêntico byte a byte ao da clássica (`harness/canvas_edit_compare.py`: MailList, Storage), harness da clássica igual.
- Tudo via `doc/store.ts`: o painel edita com `applyEdits`, a árvore seleciona com `select`, o canvas reflete `useDoc`.

## Bloco 3 (feito, 25/11/2026): atlas, textos e ferramentas do projeto

- Codex: atlas DDS (`web/src/atlas/`, `openAtlas`/`previewTexture`), canvas relendo os textos do jogo após editar, duplo clique `gf:element-dblclick`.
- Claude 2: tela de Textos (`texts_session.py`, a clássica usa o mesmo serviço), ponte de manutenção (`web_api/maintenance.py`: versões, puxar, limpar, UI oficial, erro do jogo, exportar textos, cópias do F5) e diálogos/banners. Parou no limite de uso antes de ligar os pontos de entrada.
- Principal: ligação dos pontos de entrada (cartão Continuar, menu ⋯, menu do projeto, chip da UI oficial, aviso de controles novos no F5, banner das cópias, duplo clique na árvore e no canvas, botão do atlas, prévia de textura), aviso de atualização dos textos do jogo (`game_text_updates.py` + `web_api/text_updates.py` + banner).
- Verificado: smoke 80/80, XML idêntico byte a byte (inclusive recorte pelo atlas), harness da clássica igual.
- Pendente: `insertControls` no store (Adicionar controles do oficial), posição na tela da raiz posicionada pelo jogo no painel, passos de smoke de Puxar/Limpar/Resolver erro.

## Bloco 4 (Claude 2, 25/11/2026): configurações, atualizador, manifesto, "Abrir com"

- Serviços sem Qt: `app_settings.py` (o que a tela mostra/grava/esquece, validado), `app_updates.py` (`UpdateSession`: verificar, automática de 24 h, pular, instalar; notas agrupadas como o `WhatsNewDialog`; avisos do manifesto e versão mínima), `single_instance.py` (named pipe por usuário, só JSON, autenticado).
- Ponte: `web_api/settings.py` (`settings_state/set/reset`) e `web_api/updates.py` (`update_check/auto_check/skip/install`, `manifest_notices/mark_seen`, `_on_instance_message` → evento `open_external`). O manifesto é lido no `startup` só com "Verificar ao abrir" ligado (como a clássica) e `manifest_notices` espera por ele.
- Front: `web/src/settings/` (tela com Geral/Editor/Tela/Envio/Atualizações, `UpdateDialog`, fluxos em `updates.ts`). Engrenagem → "Configurações…". Ao abrir, 2,5 s depois: atualização automática e avisos.
- Preview pelas Configurações com um XML aberto passa por `applyCanvasPreference` (mesma ponte da barra do canvas) e a casca remonta o `CanvasView` (`key=canvasEpoch`). Toda mudança dispara `gf:settings-changed` ({name, value}) em `window`.
- `main()` com `ui_mode=web`: o primeiro processo serve o pipe; o segundo manda o arquivo (`{"open": caminho}`) e sai. A clássica não mudou.

## Rodada de UI (Claude 2, 26/11/2026): atlas, Ctrl+K, código XML, AutoAnimate

- Atlas (`web/src/atlas/`): layout do `AtlasDialog` da clássica (textura à esquerda; lateral com nome e tamanho, Centralizar | Atlas inteiro, Editar posição, Estado do botão com `ui/Select` e miniatura, RECORTE NORMAL (NorUV), Abrir .dds, dica, Cursor, Fechar | Aplicar). Lógica do Codex intacta. A linha "Cursor" muda o texto direto no DOM: re-renderizar o diálogo no `pointermove` quebrava o arrasto. `ui/Select` abre a lista dentro do `<dialog>` modal quando está em um.
- Ver código XML (Ctrl+U, botão `</>` ao lado de Desfazer/Refazer): `web/src/source/` (CodeMirror 6, só leitura). Ponte `doc_source()` em `web_api/source.py` → serviço `xml_source.py` (texto do `render_text()` + linha de cada `<BaseWndProperty>`).
- Paleta Ctrl+K: `web/src/palette/` (cmdk). Busca pelo texto visível (keywords), XML e elementos só aparecem ao digitar.
- AutoAnimate (`ui/animate.ts`): projetos da tela inicial, banners, versões, Puxar, controles do oficial, escolher textura. Listas virtualizadas (Arquivos, Texturas, resultados de Textos) ficam sem.
- Engrenagem: Configurações…, Novidades, Verificar atualizações, Sobre (abre o cartão da pílula). Idioma/tema/interface ficam em Configurações e na paleta.

## XML avulso

- `ShellState.standalone_paths` contém caminhos absolutos em ordem de abertura. A sessão deduplica pelo caminho e mantém a lista até a importação de cada arquivo ou o fechamento da janela. `open_path` identifica o documento ativo. Um drop múltiplo ativa o último XML válido. Trocar de documento segue a confirmação Salvar / Descartar / Cancelar.
- `StandaloneBar` fica acima do canvas e aparece quando `open_path` está na lista. Usa `saveDocument()` para confirmar o diff e salvar no lugar, e `importStandaloneFile(path)` e `compareStandaloneFile(path)` de `doc/standaloneActions.ts`. `StandaloneFiles({ filter })` fica na página de XMLs, recebe o filtro em minúsculas e chama `openXml(path)` ao ativar uma linha.
- O drop do WebView2 chega ao callback Python do pywebview com `dataTransfer.files[].pywebviewFullPath`. A ponte emite `drop_xml` com a lista de caminhos. O front usa `open_dropped_xmls(paths)` e recebe `{ state, errors }`. O fluxo `open_external` de “Abrir com” usa essa mesma abertura para XMLs.
- `standalone_compare(path, source)` aceita `project` ou `official`. Devolve o diff unificado, `''` quando os textos são iguais ou `null` se a referência estiver indisponível.
- `standalone_pick_project()` escolhe uma pasta quando não há projeto aberto. `standalone_import(path, name, replace, bring_textures, root)` grava o conteúdo atual do editor e devolve `{ conflict, name, path }`. No sucesso inclui `{ state, doc, textures, backup }`. `doc/store.ts` promove o documento ativo para o caminho do projeto. A faixa some e os demais avulsos continuam na lista.
- `asset_base(path)` continua servindo canvas e atlas. Para avulsos, a ordem é a pasta do XML, o projeto aberto, a base oficial pelo CRC e `UI/` do jogo. A importação considera as texturas já disponíveis no projeto e na base oficial.

## Rodada de UI (Claude 2, 26/11/2026): XML avulso compreensível, tamanhos animados, dica do canvas

- Soltar arquivos: `doc/DropOverlay.tsx` ouve dragenter/dragover/drop na janela e só reage quando `dataTransfer.types` tem `Files` (árvore, seções e dnd-kit não usam arquivos). Conta pelos `items` (`text/xml`/`application/xml`; sem tipo = talvez XML). Sem nenhum XML: estado de recusa, `dropEffect = 'none'` e toast ao soltar. Some 180 ms depois do último dragover. Quem abre continua sendo o `drop_xml` da ponte.
- Avulso visível: selo "Avulso" ao lado do nome na barra superior (caminho no tooltip), chip "Avulso — C:\…\arquivo.xml" na barra de status, seção "Arquivos avulsos" no topo do painel de XMLs (pasta de origem em cinza, × fecha). `StandaloneBar` virou cartão com as três ações e uma linha de cada; coachmark na primeira vez (flag `standalone_coach_seen`).
- Ponte nova `standalone_close(path)` (`web_api/standalone.py`): tira da lista; se era o aberto, abre o último avulso restante, senão o último XML do projeto, senão nada. O front confirma Descartar antes.
- Importar: `importStandaloneFile(path, from?)` faz o voo (`doc/importFlight.ts`) até a linha `[data-file]` do projeto (ou o painel) e mostra o toast "Importado para o projeto · N texturas copiadas" (`textures` do resultado).
- Faixa "O arquivo mudou fora do editor" (`doc/ExternalChangeBand.tsx`): lê `useDoc(state => state.externalChange)` do observador do store e usa `reloadFromDisk` / `keepExternal` / `showExternalDiff`. `showExternalChange({ path, missing?, reload, keep, compare? })` continua para avisos manuais.
- Flags da interface nova: `ui_state()` devolve `flags` e `ui_set_flag(name, bool)` grava em `web_flags` (preferences.py). Em uso: `standalone_coach_seen`, `canvas_hover_tip`.
- Tamanhos animados: `ui/AnimatedSize.tsx` (NumberFlow, 380 ms, respeita reduzir movimento; o texto final fica em `data-size` porque o número vive no shadow DOM). Limpar: total sobe ao abrir, botão e "Depois de limpar" andam com a escolha (`cleanup_scan` devolve `total_bytes`). Tela inicial: tamanho que chega depois sobe de zero; o que muda (depois do Limpar) anda até o novo.
- Versões: selo "inclui ajustes de resolução" quando `resolutions > 0`. O campo conta itens (resolutions.json + variantes), não resoluções; por isso o número vai no tooltip.
- Dica do canvas (`shell/CanvasHoverTip.tsx` + `shell/canvasHover.ts`): DOM fixo por cima do canvas. O canvas só expôs duas props em `CanvasView`: `onHover(hover | null)` com `{ element, box, rect (px na janela), pointer }`, chamada no pointermove sem gesto e com null ao apertar, sair, rolar, teclar, mudar zoom/pan ou o documento; e `toolbarExtra` (nós extras na barra flutuante). Atraso 450 ms, some acima de 0,9 px/ms. Liga/desliga no (i) da barra flutuante e em Configurações → Editor.

## Exportar para várias resoluções (Claude 2, 26/11/2026)

- Serviço sem Qt: `multi_resolution.py`. Cada XML vira **pedaços** (elementos que se encostam, folga de 48 px; tamanho zero entra no mais próximo; fora da tela fica onde está). Regra por eixo, pelo terço do espaço livre: começo = mantém a distância dessa borda, fim = mantém a distância da outra, meio = mantém a proporção. Fica igual ("o jogo cuida"): janela que o jogo posiciona com a raiz no tamanho real, pedaço encostado na raiz, pedaço que já sai da tela e janela ainda não mapeada (`placement` None). Gera o XML com o mínimo: só a raiz quando tudo anda junto numa janela do jogo (como o Harlem no ElfAttack), senão os elementos do pedaço.
- Projeto: `resolutions.json` (base, resoluções marcadas, ajustes `arquivo → LxA → pedaço → [x, y]` na tela daquela resolução) e `resolutions/<LxA>/<caminho>` (arquivos só daquela resolução, ex. main.dds). Fora de `ui/`, então não entram na lista de arquivos, no F5 nem no Exportar normal; o Duplicar copia. **Ainda não** entram nas Versões do projeto.
- Ponte: `web_api/resolutions.py` (`resolutions_info/set_choice/plan/scenes/adjust/reset/add_variant/remove_variant/pick_folder/export`). As cenas são `describe_scene` do XML gerado na resolução alvo (sem User.ini), iguais às camadas de referência; a análise fica em cache até um arquivo do projeto mudar.
- Front: `web/src/resolutions/` (diálogo, prévia que importa `drawScreen`/`drawReferenceLayer` do canvas, `rules.ts` com as frases). Exportar virou botão dividido: o clique principal continua "Exportar UI (.zip)…"; a seta abre o menu com "Exportar para várias resoluções…".
- Teste de referência: `tests/test_multi_resolution.py` lê os zips do Harlem de `~/Downloads/UI_s` (ou `GF_HARLEM_UIS`) e pula sem eles.

## Próximos blocos

3. Atlas, textos (busca, edição, importar/exportar), puxar, limpar, versões, UI oficial, erro do jogo, histórico.
4. Configurações, atualizador, manifesto, empacotamento (PyInstaller com `web_dist`, WebView2 no instalador) e beta com toggle.
