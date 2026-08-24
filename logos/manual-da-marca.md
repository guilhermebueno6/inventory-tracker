# Estoque Fácil — Manual da Marca

**Versão 1 — 2026**
Aplicativo de controle de estoque para Windows e macOS.

Este documento define o símbolo, os lockups, as cores, a tipografia e os limites de uso da marca Estoque Fácil. Tudo é derivado do sistema visual Modernist: plano, sem cantos arredondados, régua de 2px e vermelho usado com parcimônia.

---

## 01 — O símbolo

Quatro barras brancas de larguras diferentes sobre um campo vermelho cheio. É um código de barras reduzido ao mínimo legível — o gesto de conferir um produto. O campo cheio garante presença na barra de tarefas do Windows e no Dock do macOS, onde ícones vazados desaparecem.

### Proporções (grade de 100 × 100)

| Elemento | Valor |
| --- | --- |
| Campo | 100 × 100, raio 0 |
| Barras — início / fim vertical | y = 20 → y = 80 |
| Larguras das barras | 10 / 16 / 8 / 20 |
| Posições x | 14 / 30 / 52 / 66 |
| Margem lateral mínima | 14 unidades |

Nunca uniformizar as larguras: o ritmo desigual é o que faz o símbolo ler como código de barras.

### Área de respiro

Respiro mínimo igual a **30% da altura do símbolo** em todos os lados. Nada entra nessa faixa — nem texto, nem régua, nem borda de botão.

### SVG de referência

```svg
<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <rect width="100" height="100" fill="#EC3013"/>
  <rect x="14" y="20" width="10" height="60" fill="#FFFFFF"/>
  <rect x="30" y="20" width="16" height="60" fill="#FFFFFF"/>
  <rect x="52" y="20" width="8"  height="60" fill="#FFFFFF"/>
  <rect x="66" y="20" width="20" height="60" fill="#FFFFFF"/>
</svg>
```

Variante de três barras (para uso abaixo de 24 px):

```svg
<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <rect width="100" height="100" fill="#EC3013"/>
  <rect x="18" y="20" width="12" height="60" fill="#FFFFFF"/>
  <rect x="40" y="20" width="16" height="60" fill="#FFFFFF"/>
  <rect x="66" y="20" width="18" height="60" fill="#FFFFFF"/>
</svg>
```

---

## 02 — Lockups

| Versão | Quando usar |
| --- | --- |
| **Horizontal** (símbolo + nome) | Padrão. Barra de título, tela de login, site, assinatura de e-mail. |
| **Empilhado** | Espaços estreitos e verticais. |
| **Wordmark** (só o nome) | Documentos, notas fiscais, contratos, texto corrido. |
| **Símbolo** | Ícone do aplicativo, favicon, avatar, etiqueta de produto. |

Nome sempre em **caixa alta, Archivo 700**, entreletra −0,035em. Assinatura opcional abaixo do nome: `CONTROLE DE ESTOQUE`, caixa alta, entreletra 0,26em, cinza.

### Tamanhos mínimos

- Símbolo: **16 px** — abaixo de 24 px use a variante de três barras.
- Lockup horizontal: **120 px** de largura.

---

## 03 — Cor

Paleta mono: tinta sobre fundo claro, com um único vermelho.

| Papel | Hex | Uso |
| --- | --- | --- |
| Vermelho | `#EC3013` | Símbolo, ação primária, pequenas ênfases |
| Vermelho escuro | `#B32309` | Texto pequeno em vermelho, estado pressionado |
| Tinta | `#201E1D` | Texto, réguas, tema escuro |
| Fundo | `#F3F2F2` | Fundo da aplicação |
| Superfície | `#FFFFFF` | Cartões, tabelas, painéis |
| Cinza texto | `#6F6863` | Rótulos, texto secundário |

### Versões do símbolo por fundo

- **Fundo claro:** campo vermelho, barras brancas (oficial).
- **Fundo escuro:** campo vermelho, barras na cor do fundo (`#201E1D`).
- **Mono preto:** campo tinta, barras brancas — para impressão em uma cor.
- **Invertido:** campo branco, barras vermelhas — sobre faixa vermelha cheia.

O vermelho sobre o fundo claro atinge cerca de 3:1 — suficiente para ícones, títulos grandes e chrome de interface, não para texto corrido. Para texto pequeno em vermelho use `#B32309`.

---

## 04 — Tipografia

Uma família só: **Archivo**, em títulos e em texto.

| Nível | Peso | Tamanho | Entreletra |
| --- | --- | --- | --- |
| Display | 700 | 44–62 px | −0,035em |
| Título | 700 | 26 px | −0,025em |
| Subtítulo | 600 | 18 px | −0,01em |
| Texto | 400 | 14 px / 1,6 | 0 |
| Rótulo | 700 | 12 px, caixa alta | 0,18em |
| Número | 700 | 34 px, tabular | −0,02em |

### Regras

- Tudo alinhado à esquerda — inclusive dentro de botões.
- Números sempre tabulares (`font-variant-numeric: tabular-nums`) em tabelas de estoque.
- Sem itálico e sem sublinhado, exceto em links.

### Voz

Técnica e seca. Frases curtas, verbo direto, sem exclamação. "Saldo atualizado." em vez de "Prontinho, tudo salvo!". O app informa; não conversa.

---

## 05 — Aplicação

- **Barra de título:** símbolo a 22 px + wordmark a 14 px, à esquerda; navegação em rótulos caixa alta à direita.
- **Ícone do aplicativo:** quadrado cheio, sem borda e sem sombra. O sistema operacional aplica a máscara que quiser — não arredonde por conta própria.
- **Tema escuro:** as barras assumem a cor do fundo; o campo vermelho nunca muda.
- **Etiquetas de produto:** símbolo mono preto, para impressão térmica em uma cor.

### O que não fazer

- Arredondar os cantos do campo.
- Trocar a cor do campo por qualquer outra que não o vermelho da marca.
- Uniformizar as larguras das barras.
- Girar, inclinar ou aplicar perspectiva.
- Adicionar sombra, brilho, gradiente ou contorno.
- Usar o símbolo sobre fotografia sem respiro sólido atrás.
