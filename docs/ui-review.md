# Por que a interface foi simplificada

## A tarefa que organiza a tela

O fluxo principal é **abrir um XML → localizar um elemento → ajustar geometria ou textura → salvar**. A tela agora usa quatro áreas com papéis claros: barra de arquivo/edição, árvore para localizar, canvas para manipular e inspetor para conferir e editar o elemento selecionado.

## Decisões e princípios

| Mudança | Por quê |
| --- | --- |
| Comandos de bloquear, ocultar e isolar ficam junto ao elemento no inspetor; continuam no menu e com atalhos. | A [proximidade](https://www.nngroup.com/articles/gestalt-proximity/) ajuda a associar uma ação ao objeto que ela afeta. A barra superior fica dedicada aos comandos gerais. |
| A barra mantém texto em Abrir e Salvar; não vira uma faixa só de ícones. | [Ícones isolados podem ser ambíguos](https://www.nngroup.com/articles/icon-usability/). Rótulos curtos tornam as ações centrais fáceis de reconhecer; os demais comandos continuam no menu. |
| O inspetor separa identificação, geometria e aparência por espaço e subtítulos. | Agrupar informações relacionadas diminui o esforço para localizar um campo. [Hierarquia visual](https://www.nngroup.com/articles/principles-visual-design/) também depende de contraste, tamanho e posição, não apenas de linhas. |
| Valores somente de leitura perderam a borda de campo editável; coordenadas mantêm borda e foco. | A borda agora comunica a possibilidade de editar. A [redução de ruído](https://www.nngroup.com/articles/aesthetic-minimalist-design/) não pode apagar a indicação de interatividade. |
| Sem seleção, o inspetor mostra apenas a orientação para selecionar um elemento. | As propriedades só aparecem quando podem ajudar na tarefa. É uma aplicação limitada de [divulgação progressiva](https://www.nngroup.com/articles/progressive-disclosure/): elas voltam imediatamente quando há seleção. |
| O frame extra do canvas foi removido; a borda do elemento selecionado permanece. | O canvas é a área de trabalho. O contorno da seleção transmite estado e facilita manipulação, então tem função. |
| O inspetor rola quando a janela fica baixa. | A [área de rolagem do Qt](https://doc.qt.io/qt-6/qscrollarea.html) preserva acesso aos campos sem impor uma altura mínima grande à janela. |

## Como avaliar a próxima mudança

1. Teste os estados **sem XML**, **XML aberto sem seleção**, **selecionado**, **bloqueado**, **oculto** e **isolado**.
2. Confira janelas menores, teclado e foco. Não dependa exclusivamente de hover para descobrir comandos.
3. Compare contraste de texto e indicadores de foco com os critérios [WCAG 2.2](https://www.w3.org/TR/wcag/). Eles são uma referência útil também para um desktop Qt, embora conformidade web não seja automaticamente conformidade do aplicativo.
4. Observe alguém que não conhece o editor tentando localizar, mover e salvar um elemento. Se a pessoa hesitar ou buscar no lugar errado, registre o passo e ajuste a hierarquia antes de adicionar decoração.

Os valores de cor continuam centralizados em `src/gf_ui_editor/theme.py`. Para este projeto, é mais útil manter alguns papéis consistentes (fundo, painel, texto, borda, foco e seleção) do que criar um grande catálogo de tokens sem uso.
