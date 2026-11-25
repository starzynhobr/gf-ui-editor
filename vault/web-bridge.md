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

## Bloco 2 (em andamento): edição

**Contrato compartilhado:** `web/src/doc/store.ts` (estado do XML aberto, seleção, edições com desfazer, salvar) e `src/gf_ui_editor/web_api/document.py` (documento em memória no Python, fonte da verdade). As assinaturas do `store.ts` não mudam sem combinar; quem implementa é o canvas.

| Parte | Arquivos | Dono |
|---|---|---|
| Documento em memória, edição, diff, salvar | `web_api/document.py`, serviços sem Qt | **Codex** |
| `doc/store.ts` (implementação) e canvas editável | `web/src/doc/`, `web/src/canvas/` | **Codex** |
| Árvore de elementos (Ctrl+3), painel de propriedades, salvar/descartar na casca, atalhos globais | `web/src/` fora de `canvas/` e `doc/`, `web_api/projects.py` | **Claude 2** |

- **Codex:** selecionar (clique, Ctrl, caixa), mover arrastando, alças de redimensionar, grupo, Shift mantém proporção, travar eixo, setas (1 px, Shift 10), encaixe em pixel inteiro, raiz que o jogo posiciona andando como a clássica (`window_geometry`), área fantasma, travados/escondidos/isolado respeitados no canvas, desfazer/refazer como lotes, salvar com backup e diff (`xml_document`), recarregar quando o XML muda no disco.
- **Claude 2:** árvore de elementos como a clássica (hierarquia, filtro via `text_preview.search_text`, esconder/travar/isolar, colunas), painel de propriedades (identificação, posição/tamanho editáveis com setas/roda desligada, textura, aparência/fonte com seletor de cor, campos só quando o controle tem o atributo), barra superior Salvar habilitado com o diff antes de gravar (como a clássica), "Descartar alterações?" ao trocar de XML/projeto/fechar, Ctrl+S/Ctrl+Z/Ctrl+Y/Ctrl+Shift+Z, F5 salvando antes.
- Tudo via `doc/store.ts`: o painel edita com `applyEdits`, a árvore seleciona com `select`, o canvas reflete `useDoc`.

## Próximos blocos

3. Atlas, textos (busca, edição, importar/exportar), puxar, limpar, versões, UI oficial, erro do jogo, histórico.
4. Configurações, atualizador, manifesto, empacotamento (PyInstaller com `web_dist`, WebView2 no instalador) e beta com toggle.
