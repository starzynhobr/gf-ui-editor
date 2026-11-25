# Como o launcher aplica uma UI

Teste feito em 25/11/2026 com a UI de teste `UICustom/TESTE-PARCIAL` (só o `Bank.xml`, com `WindowLeft` 0 → 1 no primeiro elemento).

## Passos e resultado

1. **Antes:** pasta `UI` com a STZ-UI aplicada (`Launcher.ini`: `UIAplicada=custom:STZ-UI`).
2. **Aplicou a UI-HERO** (selecionar + Jogar): 319 dos 325 XMLs da raiz ficaram iguais aos da HERO.
3. **Aplicou a TESTE-PARCIAL:** o `Bank.xml` virou o da TESTE-PARCIAL; os outros 281 XMLs que a HERO muda **continuaram os da HERO**. `UIAplicada=custom:TESTE-PARCIAL`.
4. **Reaplicou a STZ-UI:** a pasta `UI` voltou igual ao retrato do passo 1 (zero diferenças). TESTE-PARCIAL apagada.

## Conclusão

**Aplicar uma UI copia os arquivos dela por cima da pasta `UI`; o que ela não traz continua como estava.** O launcher não restaura o oficial antes. Uma UI é o conjunto de arquivos que ela contém: com 500 arquivos substitui 500, com 10 substitui 10.

```
default   STZ-UI → F5     HERO → F5      Rogue → F5
  ■         .      ■        ■     ■        ■     ■
  ■         ■      ■        .     ■ (STZ)  ■     ■
  ■         .      ■        .     ■ (def)  ■     ■
```

Consequências:
- Uma UI só com os arquivos alterados é coerente com o launcher ([D10](decisions.md)). O editor passa a enviar e exportar só o que difere do oficial ([roadmap](roadmap.md#fase-2--projetos-070-beta2-em-diante)).
- O `Launcher.ini` guarda a UI aplicada (`UIAplicada`, `UISig`).

## Referência do oficial: `GameDataFileList.txt`

Manifesto do launcher, uma linha por arquivo oficial (74.314 linhas; 19.302 da UI):

```
UI\Bank.xml|27012|CE2F48EF|1829|0|
```

Caminho | tamanho | **CRC32 do conteúdo oficial** | provável tamanho compactado | flag. O CRC confere com a cópia oficial guardada em `.official-ui/CE2F48EF.xml` (27.012 bytes). A lista muda a cada atualização do jogo; os textos de `data/Translate` estão em `GameDataFileListT.txt`.
