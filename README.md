# GF UI Editor

Editor visual para os XMLs de interface do Grand Fantasia Violet.

O MVP abre um XML em Big5, monta os elementos com as texturas DDS, permite selecionar pela tela ou pela árvore, mover por arraste ou pelas setas e editar posição/tamanho numericamente. Ao salvar, cria um backup exato e altera somente os atributos modificados no XML original.

## Executar

Requer Python 3.11 ou superior. Na primeira execução, instale as dependências em um ambiente virtual:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

No PowerShell, execute:

```powershell
.\.venv\Scripts\python.exe -m gf_ui_editor
```

Também é possível abrir um arquivo diretamente:

```powershell
.\.venv\Scripts\python.exe -m gf_ui_editor "C:\Violet Games\Grand Fantasia Violet\UI\Channel.xml"
```

O script `run.ps1` também funciona quando as dependências já estão instaladas no Python usado pelo comando `python`.

## Controles

- Clique ou árvore lateral: seleciona um elemento.
- `Ctrl` + clique: adiciona ou remove elementos da seleção; na árvore, `Shift` também seleciona intervalos.
- Arrastar qualquer item selecionado move toda a seleção como uma única ação de desfazer.
- Ao selecionar pela árvore, o elemento recebe prioridade no próximo arraste, mesmo sob outros controles; o rótulo selecionado também pode ser arrastado.
- `Alt` + clique: percorre os elementos sobrepostos naquele ponto.
- O movimento encaixa na grade de 1 pixel durante todo o arraste.
- Alça dourada no canto inferior direito: redimensiona o elemento.
- `Shift` ao mover: trava no eixo horizontal ou vertical dominante.
- `Shift` ao usar a alça dourada: preserva a proporção original do elemento.
- Botão do meio do mouse + arraste: navega pelo canvas.
- Roda do mouse: aproxima ou afasta o canvas.
- A barra inferior mostra continuamente as coordenadas X/Y do mouse no canvas.
- Setas: movem 1 pixel; `Shift` + setas movem 10 pixels.
- Pesquisa lateral: filtra por WindowID, tipo, texto, textura, ParentNode ou CtrlType.
- Bloquear/ocultar/isolar: estados temporários do editor; não alteram o XML.
- Painel direito: edita X, Y, largura e altura com atualização imediata.
- `Abrir atlas DDS`: mostra a textura inteira e marca o recorte `NorUV` do elemento.
- No atlas, arraste para escolher outro recorte ou informe X, Y, largura e altura.
- `Centralizar seleção` aproxima e enquadra o recorte atual; `Ver atlas inteiro` retorna à visão geral.
- O contorno do recorte permanece com 1 pixel de tela para permitir seleção precisa em zoom alto.
- `F5`: recarrega todas as texturas manualmente.
- Texturas DDS referenciadas pelo XML são recarregadas automaticamente quando outro programa as salva.
- `Ctrl+S`: salva com backup.
- `Ctrl+O`: abre um XML.
- `Ctrl+Z` / `Ctrl+Y`: desfaz/refaz.
- `Ctrl+Shift+L` / `Ctrl+Shift+H` / `Ctrl+Shift+I`: bloqueia, oculta ou isola a seleção.
- `F`: enquadra toda a interface.
- `I`: mostra ou oculta todos os identificadores. O elemento selecionado sempre mostra o próprio identificador.
- `T`: mostra ou oculta as texturas.

## Segurança do salvamento

- O backup fica ao lado do XML, no formato `Nome.before-gf-ui-editor-AAAAmmdd-HHMMSS.xml`.
- O programa recusa salvar se outro processo tiver alterado o arquivo desde a abertura.
- Antes de salvar, uma prévia mostra o diff exato que será gravado.
- O XML é validado antes da substituição.
- O arquivo mantém Big5, quebras de linha e formatação original; somente atributos realmente editados são substituídos.

## Como o atlas DDS é referenciado

- `BGmap` escolhe o arquivo DDS.
- `NorUVLeft` e `NorUVTop` apontam o canto superior esquerdo do recorte.
- `NorUVWidth` e `NorUVHeight` definem o tamanho do recorte dentro do DDS.
- `WindowLeft` e `WindowTop` posicionam o elemento na interface.
- `WindowHeight` é a largura visual e `WindowWidth` é a altura visual no formato do jogo.

O recorte pode apontar para qualquer região válida do DDS. A primeira versão do editor de atlas altera `NorUV`; controles com estados adicionais podem usar outras estruturas UV que ainda não são editadas visualmente.

## Gerar o aplicativo para Windows

Com o ambiente virtual criado, instale as ferramentas de build e execute o script:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[build]"
.\build.ps1
```

O executável fica em `dist\GF-UI-Editor\` e o instalador em `dist\installer\`. O script requer o Inno Setup 6 instalado. O jogo e seus arquivos não são incluídos: o editor lê as texturas DDS na pasta do XML aberto.

## Cores da interface

A paleta fica em `src/gf_ui_editor/theme.py`. O stylesheet e os desenhos do canvas/atlas usam os mesmos tokens; altere os valores ali para ajustar as cores sem procurar por literais espalhados pelo código.

As decisões de hierarquia visual e os critérios para avaliar novas mudanças estão em [`docs/ui-review.md`](docs/ui-review.md).
