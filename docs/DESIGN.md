# Sistema visual — do manual para o código

O que manda é o [manual da marca](../design-document.md). Este documento diz
**onde cada regra dele vive no código** e **onde ele foi adaptado**, com o motivo.

## Onde mexer

| Você quer mudar… | Mexa em |
| --- | --- |
| uma cor, um tamanho de fonte, a família | `src/estoque_facil/ui/marca.py` |
| a aparência de um controle (botão, tabela, aba) | `src/estoque_facil/ui/style.qss` |
| uma peça reaproveitada (faixa, cartão, lockup, régua) | `src/estoque_facil/ui/widgets/comuns.py` |
| como o app se veste ao abrir | `src/estoque_facil/ui/tema.py` |

**Regra dura:** nenhum `#RRGGBB` e nenhum nome de fonte fora de `marca.py`.
O `style.qss` usa tokens `@NOME@`, trocados por `marca.folha_de_estilo()`.
`tests/test_marca.py` quebra se uma cor escapar para dentro de uma tela.

## O que veio direto do manual

- **§01 Símbolo.** `marca.desenhar_simbolo()` pinta a grade de 100×100 com as
  larguras 10/16/8/20 nas posições 14/30/52/66. Abaixo de 24 px troca sozinho
  para a variante de três barras. É pintado, e não carregado do SVG: em 22 px o
  rasterizador arredondava as barras para larguras iguais, e o ritmo desigual é
  o que faz o símbolo ler como código de barras.
- **§02 Lockups.** `comuns.Lockup` desenha símbolo + nome com o respiro de 30%.
  Também pintado — os SVGs de lockup usam texto vivo em Archivo e sairiam sem
  nome se a fonte não registrasse.
- **§03 Cor.** A paleta inteira está em `marca.py`. Texto pequeno em vermelho
  usa `VERMELHO_ESCURO` (`#B32309`), como manda o manual.
- **§04 Tipografia.** Archivo empacotado em `resources/fontes/`, em três
  arquivos estáticos — 400, 600 e 700, exatamente os pesos que o manual usa.
  Números de tabela passam por `comuns.celula_numero()`, que liga `tnum`.
- **§05 Aplicação.** `main_window.BarraDeTitulo` — símbolo a 22 px + wordmark à
  esquerda, navegação em rótulos caixa alta à direita, régua vermelha embaixo do
  item atual. O ícone do app é quadrado cheio, sem borda e sem sombra.
- **"O que não fazer".** `border-radius` é 0 em todo o QSS, e um teste falha se
  algum valor diferente de zero aparecer.

## Onde o manual foi adaptado, e por quê

O ESCOPO.md §6 é requisito de acessibilidade — a usuária tem pouca familiaridade
digital e não enxerga bem de perto. Onde os dois documentos se cruzam, §6 ganha.

1. **Escala tipográfica em pt, não em px.** O manual dá 14 px de corpo; o §6
   exige 14 pt. Os dois batem quando se lê a escala do manual como pt: 14→14,
   título 26→26, rótulo 12→12. A hierarquia do manual fica intacta e a letra não
   encolhe.
2. **Botão de ação em caixa baixa.** O manual usa caixa alta com entreletra
   larga nos *rótulos*. Isso vale para navegação, cabeçalho de tabela e título de
   seção — todos curtos. Botões de ação ("Confirmar baixa", "Entrada de
   mercadoria") ficaram em caixa baixa: em caixa alta, frase longa a 14 pt custa
   legibilidade, e §6 não abre mão disso.
3. **Sem verde e sem amarelo.** O §6 pedia semáforo de três cores; a paleta do
   manual é mono. Venceu o manual, porque o §6 já exigia que a cor nunca fosse a
   única portadora da informação — todo estado colorido tem texto ao lado. O que
   era matiz virou peso da letra e a régua de 2px da faixa.
4. **Vermelho no foco.** O manual reserva o vermelho para ação primária e
   "pequenas ênfases". O anel de foco entra nessa segunda categoria: é pequeno,
   é transitório e é o que diz onde o teclado está.

## Por que três arquivos e não a fonte variável

A variável do Google Fonts parecia a escolha óbvia — um arquivo, todos os
pesos — e funcionou no macOS. No Linux não: o eixo `wght` dela tem **600** como
padrão e o `nameID 1` é `"Archivo SemiBold"`. O Qt sobre fontconfig lê esse
nome, então 400, 500 e 600 saíam todos do mesmo desenho e o 700 virava negrito
sintético em vez do Bold desenhado. A hierarquia do §04 desmoronava, e só na
plataforma em que ninguém estava olhando.

`packaging/fontes/gerar_estaticas.py` refaz os três estáticos a partir da
variável, com `fontTools.varLib.instancer`. Rode só quando a fonte for
atualizada — o resultado é versionado.

O teste que pega isso é `test_os_pesos_do_manual_desenham_diferente`: ele
**mede a tinta na tela** em cada peso, em vez de perguntar ao Qt qual peso ele
acha que aplicou. Perguntar não serve — o Qt devolve o peso que você pediu
mesmo quando caiu num desenho que não existe.

Detalhe de plataforma: o caminho passado a `addApplicationFont` precisa ser
absoluto. O CoreText recusa caminho relativo dependendo de onde o processo foi
aberto — silenciosamente, devolvendo `-1`.

## Conferir na tela

`tests/test_marca.py` cobre o que quebra em silêncio (fonte que não empacotou,
token sem valor, `url()` apontando para arquivo que não existe, símbolo com o
número errado de barras). Para olhar de verdade, abra o app:

```bash
python -m estoque_facil
```
