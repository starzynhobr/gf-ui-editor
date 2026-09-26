# Idiomas da interface

O editor usa português como idioma de origem e inclui traduções para inglês, espanhol e francês. A escolha fica no botão **Idioma** no canto superior direito e entra em vigor ao reiniciar o aplicativo. Para testar uma execução sem alterar a preferência salva, use `python -m gf_ui_editor --lang es_ES` (ou `en_US`, `fr_FR`, `pt_BR`).

As frases da interface usam `tr()` ou `QCoreApplication.translate()`. Os catálogos editáveis ficam em `src/gf_ui_editor/translations/gf_ui_editor_<idioma>.ts`; os `.qm` compilados são carregados pelo aplicativo e incluídos no empacotamento. Após acrescentar ou alterar frases, execute `./translations.ps1`, complete as traduções novas no Qt Linguist e execute o script novamente. Ele bloqueia traduções pendentes em todos os idiomas registrados e usa `pyside6-lupdate` e `pyside6-lrelease` do `.venv` do projeto. O `build.ps1` também executa essa verificação antes do empacotamento.

`UIElement.kind` contém um código estável, como `image` ou `progress`. Apenas a camada de apresentação converte esse código em “Imagem” ou “Image”. Atributos XML (`WindowID`, `NorUV` etc.), nomes de arquivos e textos vindos do jogo permanecem intactos. Erros do parser também mantêm sua mensagem original para código e testes; a interface usa o código do erro para mostrar uma tradução.

Para adicionar outro idioma, crie um novo catálogo `.ts` com o idioma desejado, traduza as entradas no Qt Linguist, compile-o para `.qm` e adicione o código e o nome em `LANGUAGE_NAMES`. A opção aparecerá no botão **Idioma**. O `build.ps1` já copia os `.qm` para o aplicativo Windows. A troca em tempo real exigiria atualizar os textos de janelas abertas; a seleção atual pede reinício para evitar uma interface parcialmente traduzida.

Referências: [tradução de aplicativos no Qt for Python](https://doc.qt.io/qtforpython-6/tutorials/basictutorial/translations.html) e [ferramentas de tradução do PySide6](https://doc.qt.io/qtforpython-6/tools/index.html).
