# Etapa 0: lógica do `app.py` em serviços sem Qt

Revisão: **25/11/2026**. Parte da [migração para web](migracao-web.md#ordem-de-implementação) (etapa 0). Vale mesmo que a migração não aconteça: testes mais simples e menos acoplamento.

## Regra de cada fatia

- O serviço **não importa PySide6**: nem `QSettings`, nem `QRectF`, nem `QCoreApplication.translate`. Retângulos viram tuplas `(x, y, w, h)` e textos traduzidos ficam na interface; o serviço devolve dados (números, chaves, listas).
- O `app.py` passa a **chamar** o serviço e o comportamento fica idêntico: mesmos textos, mesma ordem de diálogos, mesmos `try/except` em volta das mesmas operações.
- Cada fatia traz **testes pytest do serviço** que não abrem janela, mais um teste que confirma que importar o módulo não carrega o PySide6 (ver `tests/test_file_list.py::test_service_does_not_import_qt`).
- Os testes de interface atuais continuam passando sem mudança. Se um teste faz `monkeypatch` em um nome de `app_module` (`list_projects`, `text_editor_command`, `reference_ready`, `QFile`, `DEFAULT_UI_DIRECTORY` no `conftest.py`), o `app.py` continua chamando esse nome pelo próprio módulo, ou o teste é ajustado na mesma fatia.
- Modelos: `project.py`, `game_sync.py`, `cleanup.py`, `versions.py`, `xml_document.py`, `gamedata.py`, `release_notes.py`.

## Como o `app.py` está dividido

Mais ou menos 8,4 mil linhas:

| Linhas (aprox.) | O que é | Tem lógica para extrair? |
|---|---|---|
| 1–330 | imports, constantes, `parse_resolution`, `text_editor_command`, `load_contributors`, `contributor_items` | Sim: funções soltas, sem Qt |
| 200–1380 | diálogos (`AboutDialog`, `StzLabsPopup`, `CleanupDialog`, `PullDialog`, `VersionsDialog`, `NewProjectDialog`, `OfficialUIDialog`, `OfficialControlsDialog`) | Pouca: `NewProjectDialog._fill_publish_targets`/`_check_publish_target`/`_fill_sources` montam listas |
| 1380–1980 | comandos de undo, `PropertyPanel` | Não: são interface por natureza |
| 1980–3600 | `EditorWindow.__init__`, ações, menus, tema, atualizações, manifesto | Sim: regras de atualização e preferências |
| 3600–4480 | abrir XML, cena, textos de exemplo, camadas de referência, preview do jogo, área fantasma, modo da raiz, resolução e fundo | Sim: textos, geometria da raiz, camadas |
| 4480–5530 | árvore de elementos, seleção, mover/redimensionar, UV, textura, atlas, travar/esconder/isolar, filtro, salvar | Sim: geometria da raiz, troca de textura, filtro, família isolada |
| 5530–6540 | tela inicial, projetos (duplicar, renomear, excluir), puxar, limpar, versões, tamanhos | Sim: dados da tela inicial, tamanhos |
| 6540–7360 | sobreposições, chips, novo projeto, UI oficial, estrutura (duplicar/apagar controle), nova imagem, erro do jogo, importar, abrir projeto | Sim: criar projeto, base do oficial, erro do jogo, importar |
| 7360–7810 | lista de arquivos e seções | **Feito (fatia 1)** |
| 7810–8040 | menu de contexto, renomear/apagar/restaurar arquivo | Sim: validações e diff de restaurar |
| 8040–8320 | publicar (F5), pasta de publicação, exportar UI/textos, confirmar diff, título | Sim: publicar e textos |
| 8320–fim | `parse_args`, `main` | Só a leitura do idioma (preferências) |

`QSettings("Local", "GF UI Editor")` aparece em cerca de 45 pontos, todos no `app.py` (ver fatia 2).

## Fatias, em ordem

**Coluna "Zona":** a parte do `app.py` que a fatia edita. Duas fatias com zonas diferentes e serviços diferentes podem ser feitas em paralelo. **Independente** = não depende de outra fatia ainda aberta.

| # | Fatia | Serviço | Zona do `app.py` | Independente? | Risco |
|---|---|---|---|---|---|
| 1 | Lista de arquivos e seções | `file_list.py` (novo) | 7360–7810, 7810–7990 | — | **Feito** |
| 2 | Preferências fora do `QSettings` | `preferences.py` (novo) | ~45 pontos espalhados | **Não**: toca o arquivo todo. Fazer sozinha, entre ondas | **Passo 1 feito**; passo 2 na etapa 2 |
| 3 | Publicar (F5) e textos | `publishing.py` (novo) + `text_data.py` | `test_in_game` (8040–8170), `_text_overrides` | — | **Feito** |
| 4 | Tela inicial e projetos | `home.py` (novo) | 5720–5760, 5900–6000, 6150–6450 | — | **Feito** |
| 5 | Criar projeto, base oficial e erro do jogo | `project.py`, `game_updates.py` | 6770–6900, 7160–7240 | — | **Feito** |
| 6 | Arquivos: importar, renomear, apagar, restaurar | `file_list.py` (acrescenta) | 7237–7290, 7870–8040 | — | **Feito** |
| 7 | Textos no canvas | `text_preview.py` (novo) | 3767–3810, 3853–3900, `filter_tree` | — | **Feito** |
| 8 | Geometria da raiz e área fantasma | `window_geometry.py` (novo) ou `game_layout.py` | 4111–4300, 4559–4830 | Sim, mas evitar junto com a 7 se ela mexer em 4559 | **Alto** |
| 9 | Troca de textura e nova imagem | `textures.py` (novo) | 4956–5060, 7118–7160 | — | **Feito** |
| 10 | Atualizações e manifesto | `updater.py`, `remote_manifest.py` | 2887–3050 | — | **Feito** |
| 11 | Funções soltas do topo | `about.py` (novo) | 160–345 | Sim | Muito baixo |

### 1. Lista de arquivos e seções (feita)

- **Serviço:** `src/gf_ui_editor/file_list.py`.
- **Origem:** dados de `_rebuild_files_tree` (XMLs, texturas da pasta principal, alterados, projetos que publicam na mesma pasta, XMLs soltos sem backups, grupos camadas/alterados/todos), `_saved_section_order`, `set_section_order` (validação), `_section_dropped`, `_merge_hidden` (removido), `_move_section`, `_section_heights`, `_history_entries`, `_backup_label` (só a data do nome), `_xml_using_texture`, `_retarget_texture`. `TEXTURE_SUFFIXES` e `FILE_SECTIONS` moram no serviço e o `app.py` reimporta os dois.
- **Testes:** `tests/test_file_list.py` (13, sem janela). Na interface continuam valendo `test_file_list_sections_*`, `test_file_sections_can_be_reordered_*`, `test_renaming_a_texture_can_update_the_xml_that_use_it`, `test_refresh_updates_textures_and_file_list_*`.
- **Por que primeiro:** menor risco (funções puras ou que só leem/gravam arquivos, sem geometria nem estado da janela), e já havia testes de interface cobrindo tudo. Maior ganho: a lista de arquivos é a [etapa 4](migracao-web.md#ordem-de-implementação), e renomear/apagar textura precisam das mesmas buscas nas duas interfaces. Também abre caminho para a fatia 6.

### 2. Preferências compartilhadas fora do `QSettings` (passo 1 feito, passo 2 na etapa 2)

Hoje cada ponto faz `QSettings("Local", "GF UI Editor").value(...)` com um padrão escrito ali mesmo, e os tipos estão misturados: `"true"/"false"` em texto, `brand_seen` em bool, `last_update_check` em float, JSON em texto (`manifest_seen`, `files_section_heights`).

**Chaves:** `language`, `last_project`, `last_file/<pasta>`, `game_dir`, `game_resolution`, `game_background`, `background_mode`, `text_mode`, `navigation_style`, `tree_hidden_columns`, `publish_on_save`, `publish_confirmed`, `offer_project_on_open`, `auto_update_check`, `last_update_check`, `beta_updates`, `skipped_update_version`, `manifest_seen`, `brand_seen`, `root_mode/<arquivo>`, `files_section_order`, `files_section_heights`.

**Plano em dois passos:**
1. **`preferences.py` sem Qt**, com cada chave declarada uma vez (nome, tipo, padrão) e acesso tipado: `prefs.publish_on_save`, `prefs.last_file(pasta)`, `prefs.root_mode(arquivo)`. O armazenamento fica atrás de uma interface mínima (`get`, `set`, `remove`). No primeiro passo ela é implementada por um adaptador de `QSettings` que fica do lado Qt, então nada muda para o usuário. O `app.py` troca as ~45 chamadas por `self.prefs`.
2. **Arquivo próprio:** `%APPDATA%\STZ GF UI\settings.json`, com gravação atômica (arquivo temporário + `os.replace`). Na primeira execução sem o arquivo, uma **migração única** copia os valores do Registro e converte os tipos. O Registro fica intocado, como plano de volta. A interface clássica e a nova passam a ler o mesmo arquivo. Como há uma instância só, não existem escritas concorrentes.

**Passo 1 (feito):**
- `src/gf_ui_editor/preferences.py`: `KEYS` e `PREFIXES` declaram cada chave uma vez com tipo e padrão. Os tipos são `str`, `flag` (texto `"true"`/`"false"`), `bool`, `float` e `json` (texto JSON).
- `Preferences` dá acesso tipado (`prefs.publish_on_save`, `prefs.last_file(pasta)`, `prefs.root_mode(arquivo)`). Quando o padrão depende do contexto, há `prefs.get(nome, padrão)`: `background_mode` usa `"custom"` se há fundo próprio, e `beta_updates` usa `True` numa versão beta.
- `Store` (`get`, `set`, `remove`) e `MemoryStore` para testes.
- Chave ausente, valor corrompido ou de tipo errado caem no padrão.
- O adaptador `QtPreferenceStore` fica no `app.py`, junto com o objeto global `prefs`. Ele abre `QSettings("Local", "GF UI Editor")` a cada acesso, como antes, e grava os mesmos valores no mesmo formato. Assim, uma instalação existente lê tudo igual, e voltar para a 0.7.0 não perde nada.
- Os 46 usos de `QSettings` no `app.py` passaram pelo `prefs`; nenhum outro módulo usava `QSettings`. Nenhum teste existente foi ajustado.
- **Testes:** `tests/test_preferences.py` (10, sem Qt) e `tests/test_qt_preferences.py` (2), que conferem o formato gravado pelo adaptador e a leitura do que o código antigo gravava.

**Passo 2 (não feito, fica para a [etapa 2](migracao-web.md#ordem-de-implementação), a casca):** um `Store` em `settings.json` como descrito acima, a migração única do Registro e o `conftest.py` isolando também o caminho do JSON. A interface não muda: só troca o `QtPreferenceStore` por esse `Store`.

- **Risco:** médio. O código fica fácil, mas perder preferências do usuário é visível. A fatia toca o arquivo inteiro e conflita com todas as outras, por isso entra **sozinha**, entre duas ondas de fatias paralelas, e em dois commits (passo 1 e passo 2). O passo 2 pode esperar a [etapa 2](migracao-web.md#ordem-de-implementação) (casca), mas o passo 1 já é útil.

### 3. Publicar (F5) e textos (feita)

- **Serviço:** `src/gf_ui_editor/publishing.py` (o nome `publish` ficaria ambíguo com `Project.publish`):
  - `pending_new_controls(diffs)`: a lista do aviso de controles novos;
  - `publish_texts(project, texts_disabled, now=None) -> TextsOutcome(changed, warnings, blocked)`: carimbo `data/<stamp>` no histórico e limpeza das edições que voltaram ao original;
  - `publish_project(project, texts_disabled, progress) -> PublishOutcome(result, texts)`: UI e textos de uma vez, para a interface web;
  - `needs_launcher_selection(result, custom_name)`.

  `_text_overrides` virou `text_data.text_index_overrides(root)`.
- **Origem:** `test_in_game` (o miolo do `try`), `_text_overrides`.
- **`except OSError`:** a interface Qt continua chamando `project.publish` (dentro de `_run_with_progress`, em outra thread) e depois `publishing.publish_texts` (na thread da interface), as duas dentro do mesmo `try`. Os serviços não capturam `OSError`, então uma falha de disco nos textos continua caindo em "Falha ao publicar". O `publish_project` existe para a web e não é usado pela clássica, para não levar os textos para a outra thread.
- **Testes:** `tests/test_publishing.py` (8, sem janela, incluindo `OSError` subindo dos textos). Na interface continuam valendo `test_publish_on_save_*` e os três testes que chamam `window.test_in_game()`.

### 4. Tela inicial e projetos (feita)

- **Serviço:** `src/gf_ui_editor/home.py`. `home_projects(roots, current_root)` recebe a lista obtida no `app.py` e devolve os projetos ordenados (aberto primeiro, depois os mais recentes) com a data. O módulo também calcula o tamanho em disco, formata os tamanhos, compara caminhos e verifica se um arquivo puxado afeta o XML aberto. `relative_age(timestamp)` devolve `("now"|"minutes"|"hours"|"yesterday"|"days"|"date", valor)` para a interface traduzir.
- **Origem:** `_relative_time`, `_human_size`, `_home_projects_card` (só a ordenação), `_start_home_sizes` (só o cálculo; a thread e o `QTimer` ficam), `_is_current_project`, `pull_into_project` (cálculo de `affected`).
- **Testes:** `tests/test_home.py` cobre ordenação, tamanhos, idade relativa, comparação de caminhos, arquivos puxados e importação sem PySide6. Na interface continuam valendo `test_home_*` e `test_cleanup_recalculates_the_project_size_on_the_home_screen`.
- **Risco:** baixo.

### 5. Criar projeto, base oficial e erro do jogo (feita)

- **Serviço:** `src/gf_ui_editor/project.py` reúne a criação a partir de pasta ou `.zip` em `create_from_source`, a importação dos soltos em `Project.import_loose_files`, a leitura da base em `Project.base_bytes` e a escolha da pasta configurada do jogo em `configured_game_dir`. `src/gf_ui_editor/game_updates.py` localiza os XMLs candidatos em `locate_error`.
- **Origem:** `new_project` (função `build` e laço dos soltos), `_project_base_bytes`, `resolve_game_error` (a busca, não os diálogos), `_game_dir` (só a regra; `DEFAULT_UI_DIRECTORY` continua no `app.py` por causa do `conftest.py`).
- **Testes:** `tests/test_project.py` e `tests/test_game_updates.py` cobrem criação, base, pasta configurada, busca do erro e importação dos módulos sem PySide6. Na interface continuam valendo os testes de novo projeto e de UI oficial.
- **Risco:** baixo. A busca em segundo plano recebe `project.base_bytes` do mesmo projeto que forneceu as pastas da comparação.

### 6. Arquivos: importar, renomear, apagar, restaurar (feita)

- **Serviço:** `file_list.py` ganhou:
  - `has_invalid_chars(name)` e `rename_target(path, name) -> (target, replacing)` (extensão automática; mudar só a caixa não substitui);
  - `delete_warning(project, path) -> DeleteWarning(official, texture_users)`;
  - `import_plan(project, sources) -> (targets, replaced)`;
  - `restore_diff(path, source, current_label, restored_label) -> str`, que devolve vazio se os arquivos são iguais e deixa o `OSError` subir;
  - `restore_file(project, path, source, now=None)`: `Project.restore` no projeto, ou backup `.before-gf-ui-editor-…` + cópia num XML solto.
- **Origem:** `rename_project_file`, `delete_project_file`, `import_files`, `restore_file` (o diff e a cópia). Diálogos, perguntas e mensagens ficaram no `app.py`.
- **Testes:** `tests/test_file_list.py` (+7). Na interface continuam valendo `test_renaming_a_texture_*` e os de apagar e restaurar.
- **Import sem uso:** `difflib` ficou sem uso no `app.py` e não foi removido, pela regra de deixar a limpeza de imports para o fim da etapa.

### 7. Textos no canvas (feita)

- **Serviço:** `src/gf_ui_editor/text_preview.py`:
  - `element_text(element, mode, labels, sample) -> str | SHORT | LONG`. `labels` pode ser um dicionário ou uma função, chamada só no modo "game", como o `_game_labels` de antes. `sample` é o texto do personagem de exemplo, quando ele está visível. A interface troca `SHORT`/`LONG` por "Texto" e "Texto de exemplo bem comprido…", traduzidos;
  - `layer_text(element, labels, sample)` para as camadas de referência;
  - `search_text(element, kind, game_label)` para o filtro da árvore, que recebe o rótulo do tipo já traduzido (`kind_label` usa Qt);
  - `takes_text(element)`.
- **Origem:** `_game_text_for`, o laço de textos em `_refresh_reference_layers`, a string pesquisável de `filter_tree`. Quando calcular a amostra (personagem de exemplo visível) continua sendo decidido no `app.py`.
- **Testes:** `tests/test_text_preview.py` (8, sem janela). Na interface continua valendo `test_text_mode_draws_samples_like_the_game_and_flags_overflow`.

### 8. Geometria da raiz e área fantasma

- **Serviço:** `window_geometry.py`, ou uma seção nova em `game_layout.py`, só com tuplas: `content_bounds(elements, offsets)`, `ghost_area(root_geometry, bounds, tolerance)`, `resized_root(geometry, w, h, screen_for)`, `root_move_as_screen_move(changes, root, set_by_game, frame_on_screen, shown_at, locked)`, `root_edit_from_panel(...)`.
- **Origem:** `_content_bounds`, `_ghost_area`, `_collapsed_root`, `_resized_root`, `_without_ghost_area` (sem a mensagem), `_root_move_as_screen_move`, a conta de `edit_selected_geometry`.
- **Testes:** os de interface são a rede: `test_dragging_a_game_centered_window_*`, `test_screen_coordinates_*`, `test_game_screen_frame_*`, `test_group_resize.py`, `test_window_resize.py`, `test_canvas_framing.py`. Faltam testes novos de tabela (entrada → geometria).
- **Risco:** **alto**. Muitos efeitos colaterais no meio da conta: `_preview_default_position` desmarca uma ação e mostra mensagem, e `_root_draws_background` lê pixels do `QPixmap`. Esses dados entram como parâmetro, já calculados pela interface. É melhor fazer depois que o harness "mesma entrada, mesma saída" existir.

### 9. Troca de textura e nova imagem (feita)

- **Serviço:** `textures.py` reúne a listagem em `ui_texture_names(folder)` e a cópia em `copy_texture_for_edit(project, source, name)`, com histórico e `remember_original` nas substituições do projeto. A interface chama `backup_texture_for_edit` antes do `try` da cópia, como no fluxo anterior.
- **Origem:** `change_selected_texture` (cópias com `shutil`), `new_image` (lista de nomes).
- **Testes:** `tests/test_textures.py` (sem Qt). Na interface continuam valendo `test_texture_of_a_control_can_be_changed_undone_and_saved` e os do atlas.
- **Risco:** médio: o fluxo está misturado com menus.

### 10. Atualizações e manifesto (feita)

- **Serviço:**
  - `updater.py`: `CHECK_INTERVAL`, `due_for_check(last, now)` (24 h), `beta_default(version)` e `should_offer(version, skipped, manual)` (a versão pulada só reaparece na verificação manual);
  - `remote_manifest.py`: `MESSAGES_PER_START`, `pending_messages(manifest, beta, seen)` (no máximo 3 avisos por abertura) e `mark_seen(seen, message)`.
  - `parse_seen`/`dump_seen` não foram criados: a fatia 2 já lê e grava o conjunto em `prefs.manifest_seen`.
- **Origem:** `_automatic_update_check`, `_beta_updates_enabled`, `apply_remote_manifest`, `check_for_updates`. As leituras e gravações continuam pelo `prefs`.
- **Testes:** `test_updater.py` (+4, incluindo o de não importar PySide6, que cobre também o `remote_manifest`) e `test_remote_manifest.py` (+1). Na interface continuam valendo `test_beta_updates_toggle_*`, `test_remote_manifest_*` e `test_min_version_*`.

### 11. Funções soltas do topo

- **Serviço:** `about.py`: `parse_resolution`, `text_editor_command`, `load_contributors`, `contributor_items`, `GAME_RESOLUTIONS`.
- **Testes:** os de `test_editor_interactions.py` importam esses nomes de `gf_ui_editor.app` e fazem `monkeypatch` em `app_module.text_editor_command`/`load_contributors`. O `app.py` reimporta os nomes (`from .about import ...`) e chama pelo nome global, então o `monkeypatch` continua funcionando.
- **Risco:** muito baixo, e o ganho também é pequeno. É uma boa fatia para testar um agente novo.

## Harness "mesma entrada, mesma saída"

`harness/run.ps1` roda fluxos reais do editor (janela de verdade, XMLs do jogo) numa caixa de areia, na versão de referência (um ref do git, padrão `main`) e na árvore atual, e compara:
- **log** de passos, perguntas e avisos, em ordem;
- **arquivos gravados**, por sha1: UI do projeto, pasta UI do jogo, UICustom, `data/Translate`, `Launcher.ini`, edições de texto e quantidade de itens no histórico;
- **capturas** de cada passo, pixel a pixel.

```powershell
.\harness\run.ps1                    # referência = main
.\harness\run.ps1 -Reference migracao-web
```

- Na primeira vez, copia a UI, `data\Translate` e as listas do jogo para `%TEMP%\gf-ui-harness\pristine` (~1 GB). O jogo real só é lido.
- Projetos, bancos e preferências vão para a caixa de areia (HOME/APPDATA trocados, QSettings desviado para INI, como no `tests/conftest.py`).
- Fluxos atuais: criar projeto, abrir XML, modos de texto, filtro da árvore, mover e salvar, trocar textura (outro .dds e cópia), nova imagem com atlas, F5 com texto editado, renomear textura usada, apagar, restaurar, salvar versão e tela inicial, erro do jogo, verificar atualizações.
- Fluxo novo vai no fim de `harness/run_flows.py` (o log é comparado em ordem). Para uma fatia, rode o harness **antes** (referência = ponta da `migracao-web`) para ver que o fluxo novo passa igual nas duas e depois com a fatia.
- Em 25/11/2026: `main` (0.7.0) × `migracao-web` (fatias 1–7, 9, 10) deu tudo igual.

## Paralelo: o que o Codex pode pegar

Onda A, em paralelo, com zonas e serviços diferentes:

- **Codex:** fatia **4** (tela inicial) e fatia **5** (criar projeto, base oficial, erro do jogo). Não encostam em `file_list.py` nem nas zonas 3600–5530.
- **Claude 2:** fatia **3** (publicar) e fatia **6** (arquivos). **Feitas.**
- A fatia **11** serve para quem terminar primeiro (zona 160–345, sem conflito com ninguém).

Depois da onda A, a fatia **2** entra sozinha (passo 1 feito), seguida da **10**. A onda B vem por último: **7**, **9** e depois **8**, com cuidado.

## Como diminuir o conflito no merge

- **Uma fatia, um commit** (ou poucos), sempre a partir da ponta atual de `migracao-web`. Antes de integrar, `git rebase migracao-web`.
- **Não mover nem reordenar métodos** no `app.py`: o corpo vira a chamada ao serviço no mesmo lugar. Métodos que ficam vazios de lógica continuam existindo como fachada fina (os testes de interface chamam vários pelo nome).
- **Imports:** cada fatia acrescenta **uma linha nova própria** de import (`from . import home`), em vez de editar a linha compartilhada `from . import cleanup, file_list, game_sync, ...`. Imports que ficam sem uso saem numa fatia de limpeza no fim da etapa, não no meio.
- **Constantes** usadas por várias fatias (`TEXTURE_SUFFIXES`, `DEFAULT_UI_DIRECTORY`, `APP_NAME`) não mudam de lugar fora da fatia dona.
- **Sem formatador** no `app.py` inteiro (nada de `ruff format`/`black` geral). O diff fica restrito às linhas da fatia.
- **Fim de linha:** o checkout usa CRLF (`core.autocrlf=true`). Arquivos gerados por script devem continuar CRLF no disco para não aparecerem como mudança inteira.
- **Rodar os testes** com o `PYTHONPATH` da própria worktree (a `.venv` aponta para o `src` do checkout principal).
