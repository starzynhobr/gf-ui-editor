# Contribuindo com o GF UI Editor

Obrigado por querer ajudar. Este guia cobre como relatar problemas, sugerir recursos e enviar código.

*English summary at the end.*

## Relatar um problema

Abra uma [issue](https://github.com/starzynhobr/gf-ui-editor/issues/new/choose) com o modelo **Problema**. O que mais ajuda:

- versão do editor (**Ajuda → Sobre**) e do Windows;
- o que você fez, o que esperava e o que aconteceu;
- o XML envolvido, anexado como `.zip`, e um print da tela;
- se o problema aparece no jogo, a mensagem de erro exata (por exemplo `..\MiniInfo.cpp ERROR: ID=8301 Child control can not found!`).

Não anexe arquivos do jogo além do XML necessário para reproduzir o problema.

## Sugerir um recurso

Use o modelo **Sugestão**. Conte o que você está tentando fazer na UI, não só a solução que imaginou: muitas vezes existe um caminho mais simples dentro do editor.

## Preparar o ambiente

Requer Windows e Python 3.11 ou superior.

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m gf_ui_editor
```

Para testar com dados reais, tenha o Grand Fantasia Violet instalado. O editor não traz o jogo nem seus arquivos.

## Antes de abrir um pull request

1. **Crie um branch** a partir do `main` e mantenha o PR focado em um assunto.
2. **Rode os testes:**
   ```powershell
   .\.venv\Scripts\python.exe -m pytest
   ```
   Mudanças de comportamento precisam de teste em `tests/`. Os testes rodam sem a pasta do jogo; use arquivos criados em `tmp_path`.
3. **Traduza todo texto novo da interface.** As frases do código ficam em português (`self.tr("…")`). Depois, rode `.\translations.ps1`, complete as entradas novas de inglês, espanhol e francês em `src/gf_ui_editor/translations/*.ts` (pelo Qt Linguist ou editando o XML) e rode o script de novo. Ele recusa traduções pendentes. Veja [docs/internationalizacao.md](docs/internationalizacao.md).
4. **Preserve os XML do jogo.** O editor lê e grava em Big5 e só troca os trechos alterados; o resto do arquivo tem que sair byte a byte igual. Não reformate, não reindente e não reescreva o XML inteiro.
5. **Siga o estilo do código ao redor:** nomes e comentários em português, comentários curtos explicando o porquê, sem dependências novas sem conversar antes.
6. **Descreva o PR** pelo modelo: o que muda para quem usa o editor, como testou e prints se mexer na interface.

## Arquivos que não entram no repositório

- arquivos do jogo (`.xml` da UI, `.dds`, executáveis), exceto trechos mínimos dentro dos testes;
- builds (`build/`, `dist/`) e o `.venv`.

## Notas da versão

As novidades mostradas no app ficam em `src/gf_ui_editor/assets/release-notes.json`, nos quatro idiomas. Quem publica a versão atualiza esse arquivo; num PR, basta descrever a mudança.

## Licença

O projeto usa a [GPL-3.0](LICENSE). Ao contribuir, você concorda que sua contribuição seja distribuída sob essa licença.

---

## English summary

- **Bugs:** open an issue with the **Bug** template: editor version, steps, the XML involved (zipped) and a screenshot. For in-game errors, paste the exact message.
- **Setup:** Windows, Python 3.11+, `pip install -e ".[dev]"`, run with `python -m gf_ui_editor`.
- **Pull requests:** branch from `main`, keep it focused, run `pytest`, add tests for behaviour changes, translate every new UI string (`translations.ps1` refuses unfinished entries), and keep game XML byte-for-byte except for the edited parts (Big5, no reformatting).
- **Don't commit** game files, builds or the virtual environment.
- The project is licensed under [GPL-3.0](LICENSE); contributions are distributed under it.
