# Como lançar uma versão

Revisão: **24/11/2026**. Passo a passo do formato que já usamos (0.5.x), mais o canal beta ([plano](beta.md)). Comandos em PowerShell, na raiz do repositório.

## Como a notícia chega no Discord

**Quem posta é o site, não o GitHub nem este repositório.**

1. Publicar a release no GitHub dispara o webhook do repositório (Settings → Webhooks, evento **Releases**).
2. Ele chama `https://stzlabs.com/api/release-hook` (projeto `stz-labs`, na Vercel: `lib/releaseHook.js`, `docs/release-hook.md`).
3. O site monta o card "STZ Labs" com as notas da release e envia ao webhook do canal **#patch-notes do STZ GF UI** (variável `DISCORD_RELEASES_GF_UI_EDITOR_WEBHOOK_URL` na Vercel).

Detalhes que importam:
- O card usa o **corpo da release** (Markdown): títulos `##` viram negrito; linhas com "SHA-256" e "Baixe o instalador…" são removidas. O botão "Baixar / Download" aponta para `https://stzlabs.com/pt/projects/gf-ui-editor`.
- **Só a ação "published" de uma release não pré-lançamento posta.** Rascunhos e **pre-releases (betas) são ignorados**, e a página do site também lista só estáveis ([D07](decisions.md)).
- Editar uma pre-release para virar estável dispara a ação "released", que o hook **não** posta. Para estável, sempre criar uma release nova (`vX.Y.Z`).
- Não chegou no Discord: GitHub → Settings → Webhooks → Recent Deliveries → reenviar. Resposta 502 = falha no Discord.

## Estável

1. **Versão** em `src/gf_ui_editor/__init__.py` (`__version__ = "X.Y.Z"`).
2. **Notas** em `src/gf_ui_editor/assets/release-notes.json`:
   - o bloco atual (`version`, `date`, `notes`) vai para o topo de `history`;
   - novo `version`, `date` (AAAA-MM-DD) e `notes` nos **quatro idiomas** (`pt_BR`, `en_US`, `es_ES`, `fr_FR`), em `new` / `improved` / `fixed`, cada item `["Título curto.", "Descrição."]`.
   - O app mostra as notas de todas as versões puladas, então o histórico não pode perder entradas.
3. **Traduções e testes:**
   ```powershell
   .\translations.ps1
   ```
   ```powershell
   .venv\Scripts\python.exe -m pytest -q
   ```
4. **Commit e push** (mensagem no padrão `feat: …, release X.Y.Z`).
5. **Build** (roda o `translations.ps1`, PyInstaller e Inno Setup):
   ```powershell
   .\build.ps1
   ```
   Sai `dist\installer\GF-UI-Editor-Setup-X.Y.Z.exe`. Para a estável, copiar também com o nome fixo (o botão de download do README e do site aponta para ele):
   ```powershell
   Copy-Item dist\installer\GF-UI-Editor-Setup-X.Y.Z.exe dist\installer\GF-UI-Editor-Setup.exe
   ```
6. **SHA-256** para o corpo da release:
   ```powershell
   (Get-FileHash dist\installer\GF-UI-Editor-Setup-X.Y.Z.exe -Algorithm SHA256).Hash
   ```
7. **Corpo da release** (salvar como `dist\installer\notes.md`), no formato das anteriores:
   ```markdown
   ## O que mudou

   - **Título.** Descrição em português.

   ## What's new

   - **Title.** Description in English.

   Quem está na 0.2.1 ou posterior recebe esta versão pela atualização automática. Baixe o instalador Windows abaixo; não é necessário instalar Python. O jogo e seus arquivos não acompanham o aplicativo.

   SHA-256 do instalador: `HASH`
   ```
8. **Publicar** (cria a tag `vX.Y.Z` no `main` e dispara o post no Discord):
   ```powershell
   gh release create vX.Y.Z --target main --title "STZ GF UI X.Y.Z" --notes-file dist\installer\notes.md dist\installer\GF-UI-Editor-Setup-X.Y.Z.exe dist\installer\GF-UI-Editor-Setup.exe src\gf_ui_editor\assets\release-notes.json
   ```
   Os três anexos são obrigatórios: o atualizador baixa o instalador com versão no nome e lê o `release-notes.json` (notas traduzidas e plano B quando a API do GitHub limita); o nome fixo serve aos links de download.
9. **Conferir:** release no GitHub, card no #patch-notes, página do site e "Verificar atualizações…" numa instalação anterior.

## Beta

Mesmo fluxo, com estas diferenças:

- Versão `X.Y.Z-beta.N` (ex.: `0.7.0-beta.1`) no `__init__.py` e no `release-notes.json`.
- **Não** copiar para `GF-UI-Editor-Setup.exe`: o nome fixo é só da estável.
- Publicar como **pre-release**:
  ```powershell
  gh release create vX.Y.Z-beta.N --target main --prerelease --title "STZ GF UI X.Y.Z beta N" --notes-file dist\installer\notes.md dist\installer\GF-UI-Editor-Setup-X.Y.Z-beta.N.exe src\gf_ui_editor\assets\release-notes.json
  ```
- Não vai para o Discord nem para o site. Avisar os testadores à mão, se quiser.
- Só recebe quem marcou **Ajuda → Receber versões beta** (a partir da 0.6.0) ou instalou uma beta.
- **Promover:** lançar `X.Y.Z` estável pelo fluxo normal (release nova, não editar a beta). Quem está na beta recebe a estável automaticamente.

## Onde está cada peça

| Peça | Arquivo |
|---|---|
| Versão do app | `src/gf_ui_editor/__init__.py` |
| Notas mostradas no app | `src/gf_ui_editor/assets/release-notes.json` |
| Build | `build.ps1` (PyInstaller + `packaging/installer.iss`) |
| Atualizador | `src/gf_ui_editor/updater.py` (`releases/latest`; com beta, `/releases`) |
| Post no Discord | projeto `stz-labs`: `lib/releaseHook.js`, `docs/release-hook.md` |

## Manifesto remoto (avisos sem lançar versão)

A partir da 0.6.0, ao abrir (se "Verificar ao iniciar" estiver ligado), o editor lê `app-manifest.json` na raiz deste repositório, branch `main`:
`https://raw.githubusercontent.com/starzynhobr/gf-ui-editor/main/app-manifest.json`.
Código: `src/gf_ui_editor/remote_manifest.py`. **Nunca mudar o caminho nem o nome do arquivo**: versões antigas continuam lendo esse endereço.

Para usar: editar o arquivo, commit e push no `main`. O GitHub pode levar ~5 minutos para servir a versão nova. O teste `test_repository_manifest_is_valid` acusa JSON quebrado antes do push.

```json
{
  "schema": 1,
  "min_version": "0.6.0",
  "disabled_features": ["export_texts"],
  "messages": [
    {
      "id": "2026-12-jogo-atualizou",
      "level": "warning",
      "text": {"pt_BR": "…", "en_US": "…", "es_ES": "…", "fr_FR": "…"},
      "url": "https://stzlabs.com/pt/projects/gf-ui-editor",
      "min_version": "0.6.0",
      "max_version": "0.6.9",
      "channel": "all",
      "until": "2026-12-31"
    }
  ]
}
```

| Campo | Efeito |
|---|---|
| `min_version` | Abaixo dela, o editor pede para atualizar a cada abertura (`null` = sem mínima) |
| `disabled_features` | Desliga funções até a correção: `export_texts` (Exportar textos), `publish_texts` (o Enviar para o jogo pula os textos e envia só a UI) |
| `messages[].id` | Cada aviso aparece **uma vez** por instalação; para repetir, use um `id` novo |
| `level` | `info` ou `warning` (ícone) |
| `text` | Por idioma; sem o idioma da pessoa, cai em português, depois inglês |
| `url` | Botão "Abrir link". Só `https://` para `stzlabs.com`, `github.com/starzynhobr/…` e convites do Discord (`discord.com/invite/…`, `discord.gg/…`); outro endereço = aviso sem botão. Lista em `ALLOWED_LINKS` |
| `min_version` / `max_version` | Para quais versões o aviso vale |
| `channel` | `all`, `stable` (quem não recebe betas) ou `beta` |
| `until` | Último dia (AAAA-MM-DD) em que o aviso aparece |

Funções desligáveis:
- Só desliga o que tem um ponto de checagem no código (hoje `export_texts` e `publish_texts`). Função nova arriscada ganha um nome em `remote_manifest.py` e a checagem antes do código que pode dar problema.
- Quem decide é só o manifesto: a pessoa não desliga nada clicando. Ao clicar numa função desligada, ela só vê o aviso.
- Não fica gravado no PC: o manifesto é relido a cada abertura. Tirou da lista, a função volta na próxima abertura.
- Sem internet ao abrir, o manifesto não chega e tudo fica ligado (falha aberta).

Regras: no máximo 3 avisos por abertura; JSON inválido, sem internet ou `schema` diferente de 1 = nada acontece. Campo novo exige versão nova do app; versões antigas o ignoram. Mudança incompatível no formato → `"schema": 2` (as versões antigas passam a ignorar o arquivo inteiro).
