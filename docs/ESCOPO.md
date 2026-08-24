# Estoque Fácil — Documento de Escopo

**Projeto:** `inventory-tracker`
**Versão do documento:** 1.2 — 21/08/2026
**Objetivo:** aplicativo desktop (Windows + macOS) em Python para controle de estoque de uma loja do Mercado Livre, operado no dia a dia por uma pessoa sem familiaridade técnica.

> **Mudanças da v1.1 → v1.2:** análise do CSV de custos real (§5.3 e Anexo B) — 195 SKUs, dos quais **75 são kits**; fluxo de **transformar um item em kit dentro do app** especificado (§5.2.1); descartada a inferência automática de composição por custo (Anexo B — não funciona, e o porquê importa); custo passa a ser usado como **validador** de composição.
>
> **Mudanças da v1.0 → v1.1:** correção da análise do depósito (§2.5 — não é Full, é o estoque de casa); kits com composição promovidos para a v1; Windows definido como plataforma principal (§9).

---

## 1. Visão geral

O app resolve quatro problemas, nessa ordem de importância:

1. **Saber quanto tem de cada produto** sem depender de planilha manual.
2. **Dar baixa das vendas** importando o relatório que o Mercado Livre já gera, sem redigitar nada.
3. **Resolver o estoque compartilhado entre kits.** O catálogo tem ~200 itens, e boa parte são kits montados na hora do envio que consomem os mesmos componentes. Hoje isso é praticamente impossível de controlar em planilha — e é onde o app entrega o maior valor.
4. **Não perder os dados** — backup automático em CSV, opcionalmente no Google Drive.

Princípio que guia todas as decisões abaixo: **é melhor o app recusar uma operação duvidosa do que gravar um número errado no estoque.** Estoque errado é pior do que estoque desatualizado, porque destrói a confiança na ferramenta e a pessoa volta para a planilha.

### 1.1 Contexto operacional (confirmado)

| | |
|---|---|
| Catálogo | **195 SKUs** — 120 simples e **75 kits** (38% do catálogo) |
| Kits | **Montados na hora do envio** — não ficam prontos na prateleira |
| Estoque compartilhado | Sim. O mesmo componente é vendido sozinho **e** dentro de vários kits |
| Dados disponíveis hoje | CSV com `CUSTO; IMPOSTO; SKU` dos 195 itens. **Sem nome de produto e sem composições** |
| Estoque principal | **Casa.** Envio próprio via Correios/pontos de envio |
| Mercado Envios Full | Existe, mas é secundário — não precisa de controle detalhado |
| Máquina da operação | **Windows** |
| Máquina de desenvolvimento | macOS (Guilherme) |
| Usuários simultâneos | Um. Banco local |

### 1.2 Fora de escopo (v1)

- Emissão de nota fiscal.
- Contabilidade completa (fluxo de caixa, conciliação bancária, regime de competência). O balanço da §5.8 é gerencial: responde *"sobrou dinheiro no mês?"*, não substitui o contador.
- Multiusuário simultâneo.
- Integração com outros marketplaces (Shopee, Amazon).
- Gestão detalhada do estoque no Full.

---

## 2. Análise do relatório real do Mercado Livre

Esta seção não é teoria: veio da leitura do arquivo
`20260821_Vendas_BR_Mercado_Libre_y_Mercado_Shops_20260821_1620hs_157009074.xlsx`.
**As regras aqui são a especificação do parser.**

### 2.1 Estrutura do arquivo

| Característica | Valor observado |
|---|---|
| Aba | `Vendas BR` (única) |
| Linhas 1–4 | Texto explicativo e título. **Ignorar.** |
| Linha 5 | Cabeçalho de *grupo* mesclado (Vendas / Publicidade / Anúncios / Compradores / Envios / Devoluções / Reclamações). **Ignorar.** |
| Linha 6 | **Cabeçalho real** — 65 colunas |
| Linha 7+ | Dados, 1 linha por item vendido |
| No exemplo | 51 linhas de dados |

> **Regra de detecção do cabeçalho:** não fixar "linha 6". Varrer as 15 primeiras linhas procurando aquela que contenha a célula `N.º de venda`. Se o ML mudar o texto introdutório, o parser continua funcionando.

### 2.2 Colunas que interessam ao estoque

| # | Nome no arquivo | Uso |
|---|---|---|
| 1 | `N.º de venda` | **Chave de idempotência.** Identificador único da venda. |
| 2 | `Data da venda` | Data do movimento. Formato: `21 de agosto de 2026 16:10 hs.` |
| 3 | `Depósito` | Nome do depósito de origem — informativo (§2.5). |
| 4 | `Estado` | Status da venda. Define se abate ou não. |
| 6 | `Pacote de diversos produtos` | Informativo (Sim/Não). Não afeta o cálculo. |
| 7 | `Pertence a um kit` | Kit *do ML* (outro conceito — §5.2). No exemplo, sempre "Não". |
| 8 | `Unidades` | **Quantidade vendida.** Vem como `float` (`1.0`, `3.0`). |
| 18 | `Cancelamentos e reembolsos (BRL)` | Se preenchido, sinaliza cancelamento. |
| 19 | `Total (BRL)` | Receita líquida — usar para margem. |
| 23 | `SKU` | **Chave primária de casamento.** |
| 24 | `# de anúncio` | Código MLB (ex.: `MLB6576715502`). Chave secundária. |
| 25 | `Título do anúncio` | Nome legível, usado no cadastro automático. |
| 26 | `Variação` | Ex.: `Cor : Rosa`, `Tamanho : Grande (G)`. |
| 27 | `Preço unitário de venda` | Para margem. |
| **43** | **`Forma de entrega`** | **Classifica casa × Full (§2.5).** |
| 46 | `Transportador` | Informativo. |
| 49 | `Unidades` (bloco Devoluções) | **Devolve ao estoque** — ver §2.6. |
| 59 | `Resultado` (Devoluções) | Se a devolução foi aceita. |
| 60 | `Destino` (Devoluções) | Se voltou para o vendedor. |
| 62 | `Unidades` (bloco Reclamações) | Informativo. |

> ⚠️ **Cuidado:** as colunas 8, 49 e 62 têm **o mesmo nome** (`Unidades`) em blocos diferentes — e as 43 e 50 também (`Forma de entrega`). Ler por **índice de coluna**, nunca por nome, ou o parser pega a coluna errada. Este é o erro mais provável da implementação.

### 2.3 Achado decisivo: o relatório não é "do dia"

O arquivo de exemplo, apesar do nome `20260821`, contém vendas de **12 a 21 de agosto** — 8 dias. Ou seja, **relatórios se sobrepõem**.

Consequência de arquitetura, e a decisão mais importante deste documento:

> **A deduplicação é por `N.º de venda`, não por arquivo.**

Cada `N.º de venda` já processado fica gravado no banco. Ao importar, o app ignora silenciosamente o que já conhece e mostra apenas o que é novo. Isso significa:

- Ela pode exportar o relatório em qualquer periodicidade (diário, semanal) sem pensar nisso.
- Importar o mesmo arquivo duas vezes **não faz nada** — é seguro por construção.
- Não existe o erro "esqueci de importar terça-feira": basta pegar um período maior.
- Não é preciso hash de arquivo nem controle de "última data importada".

Isso elimina, de uma vez, a maior classe de erro operacional do app.

### 2.4 Casamento produto ↔ linha do relatório

Cascata, na ordem:

1. **`SKU`** (col. 23), normalizado: `strip()` + `lower()`.
   No exemplo o SKU está **100% preenchido** e a nomenclatura já é consistente (`pamperspants.G28`, `KIT.MAOPE.ROSA`, `kit.travesseirosazul`).
   ⚠️ O caixa varia entre SKUs — **comparação obrigatoriamente case-insensitive**. Basta ela cadastrar um produto com caixa diferente do anúncio para o mesmo item virar dois cadastros.
2. **`# de anúncio` + `Variação`** — para anúncios sem SKU.
3. **De-para manual aprendido** — se ela vincular uma linha órfã a um produto, o app grava esse vínculo e nunca mais pergunta.
4. **Não casou** → linha fica pendente, destacada, sem afetar estoque.

### 2.5 Casa × Full — como classificar (corrigido na v1.1)

A versão 1.0 deste documento concluiu, pelo nome do depósito (`Carapicuíba Alameda dos Babaçu`), que as vendas eram Full. **Estava errado.** A verificação nas colunas de envio mostrou:

| Coluna | Valor nas 51 linhas |
|---|---|
| `Forma de entrega` (43) | `Correios e pontos de envio` — 51/51 |
| `Transportador` (46) | `Mercado Envios` (47), `J&T Express Brazil` (3), `IMILE DELIVERY` (1) |

`Correios e pontos de envio` é **envio pelo vendedor**. Logo, `Carapicuíba Alameda dos Babaçu` é **o depósito dela** — o endereço de estoque cadastrado no ML — e todas essas vendas abatem do estoque de casa.

**Lição para o parser:** classificar por **`Forma de entrega` (col. 43)**, nunca pelo nome do depósito, que é texto livre definido pelo vendedor.

```
Forma de entrega contém "Fulfillment" ou "Full"  →  local FULL
qualquer outro valor                             →  local CASA (padrão)
```

**Decisão de escopo:** como o Full é secundário e não precisa de controle detalhado, a v1 fica assim:

- O estoque continua modelado por **produto × local** (o campo existe, é barato agora e caro de retrofitar).
- Só o local **`CASA`** aparece na interface. É o número que importa.
- Vendas classificadas como Full **não abatem de `CASA`** — vão para o local `FULL`, que fica apenas contabilizado em segundo plano.
- Se aparecer uma venda Full, o app registra e **avisa uma vez**: *"3 vendas saíram do estoque Full e não foram descontadas do estoque de casa."* Sem tela, sem configuração.
- O fluxo "Enviar para o Full" (transferência `CASA` → `FULL`) fica na fase 2, para quando ela repor o Full.

Isso dá o comportamento correto sem custar complexidade na tela.

### 2.6 Devoluções

As colunas 49–61 existem mas vieram vazias no exemplo (célula = `' '`, um espaço). O parser deve:

- Tratar `''`, `' '` e `None` como vazio (**normalização obrigatória** — o ML preenche células "vazias" com espaço).
- Quando `Unidades (Devoluções)` > 0 **e** `Destino` indicar retorno ao vendedor → gerar movimento de **entrada**, com `N.º de venda + ":dev"` como chave de idempotência.
- **Devolução de kit volta como componentes**, espelhando a baixa original (§5.2).
- Não presumir os textos exatos de `Resultado`/`Destino`: deixar a lista de valores que contam como "voltou ao estoque" em **configuração**, e marcar como pendente de revisão quando aparecer um valor desconhecido.

### 2.7 Outros detalhes do formato

- **Datas em português por extenso** (`21 de agosto de 2026 16:10 hs.`). Parse com tabela de meses própria — não depender de `locale`, que não é confiável entre Windows e macOS. Se falhar, cair para a data do nome do arquivo, e por último para a data de hoje.
- **`Unidades` é `float`** → converter para `int` com validação (rejeitar fracionário).
- **Valores negativos** em tarifas (col. 12, 14) são normais.
- **Status observados:** `Pronta para emitir NF-e da venda`, `Para enviar no dia 24 de agosto`. Ambos abatem.
  **Regra:** manter uma lista de status que **não** abatem (cancelada, não concretizada) em configuração. Status desconhecido → **abate, mas marca a linha para revisão**. Nunca falhar silenciosamente.

### 2.8 Bônus: carga inicial a partir do próprio relatório

Como o relatório traz SKU + título + MLB + variação de tudo que vendeu, a primeira execução pode oferecer:

> **"Encontrei 16 produtos que você vendeu. Quer criar o cadastro deles agora?"**

Cria o catálogo com quantidade zero e ela só preenche as quantidades contando a prateleira.

⚠️ Com kits na v1, há um passo a mais: os itens criados assim entram como **simples**. Ela precisa depois marcar quais são kits e montar a composição. O app deve **sugerir** os candidatos — SKU começando com `kit` ou título começando com "Kit" acerta a maioria (`KIT.MAOPE.ROSA`, `kit.travesseirosazul`, `kit.livros.4amigosdomar`, `caixahuggies.lenço`, `pamperspantsM+lenço`). Sugerir, nunca decidir sozinho.

---

## 3. Stack e decisões técnicas

| Camada | Escolha | Por quê |
|---|---|---|
| Linguagem | **Python 3.12** | Requisito. |
| Interface | **PySide6 (Qt 6)** | Aparência nativa nos dois sistemas; `QTableView` com modelo aguenta milhares de linhas; estilização por QSS permite fontes e botões grandes; licença LGPL. Alternativas descartadas: Tkinter (tabelas fracas), Flet (empacotamento imaturo). |
| Banco | **SQLite** em modo WAL | Zero instalação, arquivo único, fácil de copiar e restaurar. 200 itens é trivial. |
| ORM | **SQLAlchemy 2.0** | Migrar para Postgres depois, se um dia precisar, sem reescrever. |
| Migrações | **Alembic** | Essencial: com auto-update, versões novas precisam evoluir o banco da usuária sem perder dados. |
| Leitura XLSX | **openpyxl** (`read_only=True`) | **Não usar pandas** — adiciona ~60 MB ao executável sem ganho real aqui. |
| Caminhos do SO | **platformdirs** | Ver §3.1. |
| Segredos | **keyring** | Token do Google no Credential Manager (Windows) / Keychain (macOS). |
| HTTP | **httpx** | Updater e, na fase 3, API do ML. |
| Logs | **logging** + `RotatingFileHandler` | Diagnóstico remoto sem acesso à máquina. |
| Testes | **pytest** | Ver §11. |
| Empacotamento | **PyInstaller** (`onedir`) | Ver §9. |

### 3.1 Onde ficam os dados

Nunca ao lado do executável (em Windows, `Program Files` é somente leitura). Via `platformdirs`:

- **Windows:** `%LOCALAPPDATA%\EstoqueFacil\`
- **macOS:** `~/Library/Application Support/EstoqueFacil/`

```
EstoqueFacil/
├── estoque.db            # SQLite
├── config.json           # preferências
├── backups/              # CSV automáticos, retenção 30
├── importados/           # cópia dos XLSX processados (auditoria)
├── fotos/                # imagens de produto
└── logs/app.log
```

---

## 4. Modelo de dados

### 4.1 Princípio: livro-razão imutável

Estoque **não** é um campo que se soma e subtrai. É a **soma dos movimentos**.

`saldo.quantidade` existe apenas como cache para a tela ser rápida, e é sempre recalculável a partir de `movimento`. Isso dá de graça:

- Histórico completo: "por que esse produto está com 3?"
- **Desfazer importação** com um clique.
- Detecção de inconsistência (teste automatizado: soma dos movimentos == cache).

Movimentos **nunca** são editados nem apagados. Correção = novo movimento de ajuste.

### 4.2 Segundo princípio: só componentes têm estoque

Como os kits são montados na hora do envio, **kit não tem estoque próprio**. O que existe fisicamente na prateleira são os componentes.

> `disponivel(kit) = min( saldo(componente) ÷ quantidade_necessária )` para todos os componentes

Isso não é uma escolha estética — é o que faz o app responder corretamente a "posso vender mais 3 kits rosa?". E resolve o problema que planilha nenhuma resolve: quando o mordedor-pé rosa acaba, o app sabe **sozinho** que o `KIT.MAOPE.ROSA` foi a zero.

### 4.3 Tabelas

**`produto`**
```
id, sku (único, case-insensitive), codigo_barras, nome, tipo,
ml_item_id, variacao, unidade, custo_medio, preco_venda,
estoque_minimo, localizacao, foto, ativo, observacoes,
criado_em, atualizado_em
```
- `tipo`: `simples | kit`
- Um produto `simples` pode ser vendido sozinho **e** ser componente de vários kits. É o caso dela (`mord.mao.azul` vende sozinho e entra no `KIT.MAOPE.AZUL`).
- `estoque_minimo` só faz sentido em `simples`. Para kits, o alerta é derivado.

**`composicao`** — a tabela central do app
```
id, kit_id → produto, componente_id → produto, quantidade
```
- Restrições: `componente.tipo = 'simples'` (**sem kit dentro de kit na v1** — recusar com mensagem clara, evita ciclos e confusão); `quantidade >= 1`; par (`kit_id`, `componente_id`) único.

**`local_estoque`** — `CASA` (padrão, visível), `FULL` (segundo plano).
```
id, codigo, nome, tipo (proprio|marketplace), visivel, ativo
```

**`saldo`** — cache, uma linha por produto **simples** × local.
```
produto_id, local_id, quantidade, atualizado_em
```
Kits não têm linha aqui. O disponível é calculado.

**`movimento`** — o livro-razão. Só de produtos simples.
```
id, produto_id, local_id, tipo, quantidade (com sinal),
saldo_apos, origem, referencia_externa, produto_vendido_id,
lote_id, observacao, criado_em
```
- `tipo`: `venda | devolucao | compra | ajuste | inventario | transferencia_saida | transferencia_entrada | cancelamento`
- `origem`: `manual | importacao_ml | importacao_planilha | api_ml`
- `referencia_externa`: o `N.º de venda`.
- **`produto_vendido_id`**: quando a venda foi de um kit, guarda **qual kit** originou a baixa do componente. É o que permite o histórico dizer *"saiu 1 mordedor-pé rosa porque vendeu 1 KIT.MAOPE.ROSA"* — sem isso, ela olha o histórico e não entende de onde o movimento veio.
- **Índice único parcial** em (`origem`, `referencia_externa`, `tipo`, `produto_id`) → idempotência garantida pelo banco, e não pela aplicação. O `produto_id` no índice é obrigatório: uma venda de kit gera **vários** movimentos com a mesma `referencia_externa`.

**`lote_importacao`**
```
id, arquivo_nome, arquivo_hash, tipo, periodo_inicio, periodo_fim,
linhas_total, linhas_novas, linhas_ignoradas, linhas_pendentes,
status (rascunho|confirmado|desfeito), criado_em, confirmado_em
```

**`vinculo_ml`** — de-para aprendido.
```
id, chave (sku_ml | mlb+variacao), produto_id, criado_em
```

**`config`** — `chave, valor`

### 4.4 As tabelas do dinheiro

Quantidade e valor são **tabelas separadas**, de propósito. `movimento` responde *"quanto tem"*; `venda_item` responde *"quanto entrou"*. Misturar as duas quebraria o invariante do estoque na primeira venda de kit — uma venda de kit gera **N movimentos** (um por componente) e **uma** linha de dinheiro.

**`venda_item`** — o dinheiro de cada linha do relatório do ML.
```
id, numero_venda, sku_ref, produto_id (pode ser nulo), titulo,
quantidade, devolvidas, abateu_estoque, cancelada, local_codigo,
preco_unitario, receita_produtos, receita_envio, tarifa_venda,
tarifa_envio, descontos, cancelamentos, total_liquido,
custo_unitario, imposto_unitario,
data_venda, lote_id, criado_em, atualizado_em
```
- **Chave**: (`numero_venda`, `sku_ref`) única. O `sku_ref` está na chave pelo mesmo motivo que `produto_id` está na chave do movimento: uma venda com vários produtos traz N linhas com o mesmo N.º de venda.
- **`custo_unitario` e `imposto_unitario` são fotografia**, gravados na criação e nunca reescritos. Mudar o custo de um produto hoje não pode alterar o lucro de um mês já fechado. Para kit, o custo é a **soma dos componentes** (`kits.custo_montado`), porque é isso que sai da prateleira.
- **Toda** linha do relatório é gravada, inclusive cancelada e sem produto casado: a receita existe de verdade, e escondê-la daria um lucro que não existe. O balanço conta quantas linhas estão sem custo e avisa na tela.
- Ao contrário do movimento, esta linha **é atualizada** quando o mesmo N.º de venda volta em outro relatório. Relatórios se sobrepõem (§2.3), e a venda de ontem pode voltar hoje cancelada ou devolvida — o balanço precisa do número mais recente. Desfazer uma importação apaga as linhas que **aquele lote criou**.
- As colunas 9 a 18 do relatório somam exatamente a coluna 19 (`Total (BRL)`) — conferido nas 51 linhas do arquivo real. É a checagem que denuncia leitura de coluna errada (§2.2).

**`despesa`** — o que a loja gastou fora da mercadoria.
```
id, data, descricao (obrigatória), categoria, valor (> 0), observacao, criado_em
```
- **Compra de mercadoria não entra aqui.** Ela vira custo quando o produto é vendido (CMV). Se entrasse, o mês da reposição apareceria no prejuízo e o mês da venda com lucro irreal.
- Descrição é obrigatória: *"R$ 300,00"* sem o quê não serve para nada três meses depois.
- Despesa é digitada à mão, então **apagar é a correção certa** — diferente de movimento de estoque, que nunca some do histórico.

---

## 5. Fluxos principais

### 5.1 Importar vendas — o coração do app

Sete passos, e o quarto é o que garante que nada saia errado:

1. **Arrastar o XLSX** na janela, ou botão grande **"Importar vendas"**.
2. **Ler e normalizar** conforme §2.
3. **Deduplicar** por `N.º de venda`. Já conhecidos são separados em "já processadas".
4. **Explodir kits** — cada linha de venda de kit vira N baixas de componentes (§5.2).
5. **Tela de conferência** — nada foi gravado ainda:

   | | |
   |---|---|
   | 🟢 **Prontas** | Casaram, com saldo suficiente. Kits mostram os componentes recolhidos. |
   | 🟡 **Atenção** | Saldo vai ficar negativo, ou status desconhecido, ou venda Full. |
   | 🔴 **Sem cadastro** | SKU não existe, **ou é um kit sem composição definida**. |
   | ⚪ **Já processadas** | Recolhido, só o número. |

   Resumo no topo, em linguagem direta:
   **"38 vendas novas → 61 unidades a baixar em 22 produtos. 2 kits ainda sem composição."**
6. **Resolver as pendências** ali mesmo — vincular, cadastrar produto, ou montar a composição de um kit sem sair da tela. Cada vínculo criado é aprendido para sempre.
7. **Confirmar** → tudo gravado em **uma transação única**. Ou entra tudo, ou nada.
8. **Desfazer** disponível na tela de importações — reverte o lote inteiro, componentes incluídos.

**Kit sem composição:** bloqueia só aquela linha, nunca a importação inteira. As outras vendas passam normalmente.

**Saldo negativo:** avisa com destaque mas **não bloqueia**. Estoque negativo é informação real (algo não foi cadastrado), e travar a importação faria ela desistir do app. Fica marcado em vermelho na tela principal até ser ajustado.

### 5.2 Kits e composição — a funcionalidade central

Confirmado que os kits são montados na hora do envio e compartilham componentes. Isso é a razão de existir do app: **é exatamente o cenário que planilha não resolve.**

Nos dados reais, kits são a maior parte do movimento — `KIT.MAOPE.ROSA` sozinho é 13 das 51 vendas (25%), e `mord.mao.azul` aparece vendido sozinho **e** como componente de kit.

### 5.2.1 Transformar um item em kit — o fluxo dentro do app

**Todo produto nasce simples.** Virar kit é uma ação explícita na tela do produto, porque com 75 kits para configurar isso vai ser feito dezenas de vezes e precisa ser rápido.

Na tela do produto, um botão: **"Transformar em kit"**. Ao clicar, o app já abre o editor **com sugestões prontas** (§5.2.2):

```
KIT.MAOPE.ROSA          custo cadastrado: R$ 13,50

  Este kit é montado com:
  ┌────────────────────────────────┬─────┬─────────┬──────────┐
  │ mord.mao.rosa                  │  1  │ R$ 6,75 │ tem 14   │  [x]
  │ mord.pe.rosa                   │  1  │ R$ 6,75 │ tem  6   │  [x]
  └────────────────────────────────┴─────┴─────────┴──────────┘
    soma dos componentes: R$ 13,50  ✅ bate com o custo do kit

  Sugestões (clique para adicionar):
    + manta.rosa (R$ 11,90)   + cueiro.rosa (R$ 17,53)   + babador.rosa (R$ 21,90)
    🔍 [ procurar outro item______________ ]

  ✅ Dá para montar 6 kits    ⚠️ limitado por: mord.pe.rosa

                              [ Cancelar ]  [ Salvar ]
```

Três coisas nessa tela merecem atenção:

- **A linha "soma dos componentes"** compara com o custo cadastrado do kit. Se divergir, avisa: *"faltam R$ 6,75 — esqueceu algum item?"*. É uma conferência de graça que pega composição incompleta (§5.2.3).
- **As sugestões** vêm ranqueadas por semelhança de nome e economizam a busca na maioria dos casos (§5.2.2).
- **"Dá para montar 6" / "limitado por X"** é o que ela vai olhar todo dia. Em uma frase, o app diz o que comprar.

#### Regras da conversão

Converter um produto que já tem histórico exige cuidado. O app trata cada caso explicitamente:

| Situação | O que o app faz |
|---|---|
| Produto tem **saldo > 0** | Kit não pode ter estoque próprio. Pergunta: *"Você tem 4 unidades desse item em estoque. Elas já estão montadas?"* → **Sim**: gera a desmontagem (devolve os componentes ao estoque e zera o kit). **Não**: gera um ajuste zerando, com observação. |
| Produto **já é componente de outro kit** | **Bloqueia.** *"Este item faz parte de KIT.X e KIT.Y. Remova de lá antes de transformá-lo em kit."* (sem kit dentro de kit — §4.3) |
| Produto tem **movimentos passados** | Ficam intactos. São fato histórico; a conversão vale daqui para frente |
| Composição **vazia** | Não deixa salvar. Kit sem componente teria disponibilidade indefinida |
| **Voltar kit → simples** | Permitido. Avisa que o estoque começará em zero e que a composição será descartada |

#### Trabalhar os 75 kits em lote

Um assistente por produto seria lento demais para 75 kits. A tela **"Kits sem composição"** lista todos os pendentes com contador (*"faltam 63 de 75"*), e ela vai descendo a lista sem voltar ao menu. Some da tela quando chega a zero.

Complemento: **importar composições por planilha** (`kit;componente;quantidade`), para o caso de ela preferir montar a lista no Excel — ou de o Guilherme montar por ela.

### 5.2.2 Sugestão de componentes por nome

Os SKUs dela são descritivos, e isso é aproveitável. `kit.mantamordedorazul` contém "manta", "mordedor" e "azul"; casando esses pedaços contra os SKUs simples, os candidatos certos sobem ao topo.

Testado contra o catálogo real (Anexo B):

| Kit | Top sugestões |
|---|---|
| `kit.mantamordedorazul` | mord.pe.azul (100%), manta.azul (100%), mord.mao.azul (67%) |
| `kit.naninha.manta.girafa` | NANINHA.GIRAFA (100%), manta.rosa (50%), manta.pink (50%) |
| `KIT.CUEIROPAMPERSROSA` | cueiro.rosa (100%), pamperspants.P (100%), pamperspants.M (100%) |

Nos três casos os componentes corretos estão entre os primeiros. **Não acerta sozinho** — em `KIT.CUEIROPAMPERSROSA` ela ainda escolhe qual tamanho de Pampers — mas troca "procurar entre 120 itens" por "clicar em dois". É a diferença entre uma tarde e uma semana de cadastro.

Regra de ouro: **sugerir sempre, decidir nunca.**

### 5.2.3 Custo como conferência

O CSV traz o custo de todos os 195 SKUs, e nos kits que dá para verificar o custo do kit é exatamente a soma dos componentes:

```
KIT.MAOPE.ROSA (R$ 13,50) = mord.mao.rosa (6,75) + mord.pe.rosa (6,75) = R$ 13,50  ✅
```

Isso não serve para *descobrir* a composição (Anexo B explica por que não), mas serve muito bem para **conferir** a que ela montou: se a soma não bate, provavelmente falta um item ou a quantidade está errada. Aviso, nunca bloqueio — o custo pode estar desatualizado, e travar por isso seria pior.

### 5.2.4 Kits na tela de estoque e alerta em cascata

Kits aparecem com **"Dá para montar: 6"** no lugar da quantidade, com ícone distinto e filtro *Simples / Kits / Todos*.

**Alerta em cascata.** Quando um componente cruza o mínimo, o alerta mostra o efeito real:

> ⚠️ **Mordedor Pezinho Rosa: 6 unidades** (mínimo: 10)
> Isso limita: **KIT.MAOPE.ROSA** (6 possíveis) e **KIT.MAOPE.COMBO** (3 possíveis)

Um item comprado destrava vários anúncios. É a informação de compra mais valiosa do app, e é impossível de obter na mão com 195 itens e 75 kits.

### 5.2.5 Regras invioláveis

- Kit **não tem estoque próprio**. Nunca. Ajuste manual em kit é recusado com explicação.
- **Sem kit dentro de kit** na v1.
- Ao apagar/desativar um componente usado em kits, avisar quais kits quebram.
- Mudar a composição **não** altera movimentos passados — o histórico registra o que saiu de fato.
- Um produto simples continua vendável sozinho, sem nada especial.

### 5.2.6 Tirar um produto do catálogo — arquivar × excluir

O catálogo inicial vem do Mercado Livre e traz anúncios que ela já não vende. Precisa dar
para limpar a lista — sem que limpar a lista signifique reescrever o passado.

São **duas operações**, e o app escolhe qual cabe (a usuária nunca precisa saber a
diferença: ela clica em *Excluir* e o app pergunta uma coisa só):

| | Quando | O que acontece |
|---|---|---|
| **Excluir de vez** | O produto nunca foi movimentado | A linha some do banco, junto com a composição, se for kit. Sem volta. |
| **Arquivar** | O produto tem histórico | Some das listas, buscas, contadores e alertas. Movimentos e saldo ficam intactos. Reversível. |

**Por que não apagar sempre.** O §4.1 diz que estoque é a soma dos movimentos. Apagar um
produto com histórico deixaria vendas antigas sem o item que saiu — o número pararia de
bater com a realidade e o *Conferir estoque* passaria a acusar diferença para sempre.
Nas chaves estrangeiras do banco isso é literal: nem `movimento.produto_id` nem
`venda_item.produto_id` têm cascata, então o SQLite recusaria. O app recusa antes, em
português.

**"Histórico" são as duas tabelas.** `movimento` (quantidade) e `venda_item` (dinheiro,
§4.4) contam juntos. Não é detalhe: uma venda **cancelada** grava a linha de dinheiro e
**nenhum** movimento de estoque. Olhar só para `movimento` deixaria esse produto passar
como "nunca movimentado" e o `DELETE` morreria na chave estrangeira — erro técnico na
cara da usuária, sem explicação e sem saída.

**Componente usado em kit não sai** — nem excluído, nem arquivado. A mensagem nomeia os
kits que quebrariam e manda removê-lo dessas composições primeiro (é a regra do §5.2.5
levada ao pé da letra). Kits arquivados aparecem marcados na mensagem, senão ela mandaria
procurar um kit que sumiu das listas.

**Arquivado que vende de novo.** A importação continua baixando o estoque — a venda é
real —, mas a linha entra como 🟡 *Atenção* dizendo que o produto está arquivado. Sem isso,
arquivar viraria um buraco silencioso no estoque.

O filtro *Arquivados* na tela de estoque lista os arquivados e traz qualquer um de volta,
com o estoque e o histórico que ele já tinha.

### 5.2.7 ⚠️ Consequência: o estoque dos anúncios no ML fica errado

Com componentes compartilhados, vender 1 `KIT.MAOPE.ROSA` reduz a disponibilidade do anúncio do mordedor avulso — **e o ML não sabe disso**. Risco real de vender o que não existe.

Na v1 o app faz o que dá sem API: destaca na tela inicial os anúncios cuja disponibilidade calculada divergiu, para ela ajustar no ML manualmente.

**Esta é a justificativa mais forte para a API do Mercado Livre na fase 3** — o passo que fecha o ciclo, atualizando o estoque de todos os anúncios afetados automaticamente. Vale registrar desde já como o objetivo final do projeto.

### 5.3 Carga inicial do catálogo

Os 195 SKUs entram por importação, em três passos que o app conduz na primeira execução:

**Passo 1 — CSV de custos.** O arquivo que já existe (`CUSTO; IMPOSTO; SKU`, separador `;`, decimal `.`, UTF-8) cria os 195 produtos com custo e imposto. Todos entram como **simples**, estoque zero.

**Passo 2 — nomes.** ⚠️ **O CSV não tem nome de produto**, só SKU. Um catálogo de `pamperspants.G28` e `KIT.MAOPE.ROSA` é operável por quem criou os códigos, mas ruim para conferir na prateleira.

> **Recomendação prática:** exportar do ML um relatório de vendas de **90 dias ou mais**. Ele traz `SKU + Título do anúncio`, e o app preenche os nomes automaticamente por cruzamento. O relatório de 8 dias que temos cobre só 16 dos 195 SKUs; um trimestre deve cobrir a maior parte do que gira. O resto ela nomeia aos poucos — o app mostra "sem nome" como pendência leve, sem atrapalhar.

**Passo 3 — marcar os kits.** O app propõe os 75 candidatos pela heurística do nome (SKU contendo `kit` ou `+`) e ela confirma em lote — uma tela com caixas já marcadas, ela só desmarca os falsos positivos (`pompomM.kitchabebe`, `pampers.kitchadebebe` parecem kits mas podem não ser). Depois entra na tela "Kits sem composição" (§5.2.1).

**Ordem obrigatória:** produtos antes de composições, e composições antes de importar vendas. O assistente força essa ordem — se ela importar vendas com kits ainda vazios, as linhas de kit ficam pendentes (§5.1) e o trabalho tem que ser refeito.

### 5.4 Entrada de mercadoria (compra)

Formulário simples: produto, quantidade, custo unitário, fornecedor, data.
Atualiza `custo_medio` por **média ponderada**.
Depois de lançar, mostrar o efeito: *"Isso destravou 12 kits a mais."*

### 5.5 Inventário e ajustes manuais (perda, quebra)

Lista os produtos **simples** (kits não se contam), ela digita o que contou, o app gera os ajustes e mostra o resumo das diferenças. É o que traz o estoque de volta à realidade quando ele desanda.

Junto vem o ajuste avulso, para o que sai sem venda. O **motivo não é enfeite**: ele decide o tipo do movimento, e o tipo decide se aquilo custa dinheiro no balanço.

| Motivo | Tipo gravado | Efeito no estoque | Entra no balanço? |
|---|---|---|---|
| Quebrou ou estragou | `perda` | sai | **sim**, a custo |
| Sumiu / não achei | `perda` | sai | **sim**, a custo |
| Brinde ou uso próprio | `perda` | sai | **sim**, a custo |
| Voltou danificado | `perda` | sai | **sim**, a custo |
| Achei mais do que tinha | `ajuste` | entra | não |
| Contei a prateleira | `inventario` | vai ao número exato | não |

Perda é tipo próprio, e não `ajuste` genérico, exatamente para o balanço poder dizer *"R$ 84,00 perdidos em quebra este mês"*. A perda é valorizada pelo **custo atual** do produto — ela não passa por venda, então não existe fotografia de custo para ela.

### 5.6 Cadastro rápido

Formulário curto: nome, código, quantidade. Tudo o mais é opcional, recolhido atrás de *"Mais opções"*. Salvar e cadastrar outro sem sair da tela.

### 5.7 Envio para o Full (fase 2)

Transferência `CASA` → `FULL`. Ver §2.5.

### 5.8 Balanço do período (PNL)

A tela responde **uma** pergunta — *sobrou dinheiro no mês?* — e a resposta aparece primeiro, em uma frase: *"Sobrou R$ 1.234,56 em agosto — margem de 21% sobre R$ 5.900,00 vendidos em 51 vendas."* A conta que leva até ela vem abaixo, na ordem de um DRE simples, para conferir de cima para baixo com o extrato do ML:

```
  Vendas de produtos                   col. 9 do relatório
+ Frete cobrado do comprador           col. 13
± Descontos e bônus                    col. 10 + 17
− Cancelamentos e reembolsos           col. 18
− Tarifas do Mercado Livre             col. 12 + 11 (parcelamento)
− Custos de envio                      col. 14 + 15 + 16
─────────────────────────────────────
= Recebido do Mercado Livre            col. 19 — bate exatamente
− Custo dos produtos vendidos (CMV)    custo fotografado na venda
− Impostos sobre as vendas             IMPOSTO do catálogo, por unidade
− Perdas e quebras                     movimentos tipo `perda`, a custo
− Despesas da loja                     tabela `despesa`
─────────────────────────────────────
= Lucro do período
```

Três decisões que sustentam isso:

1. **O balanço é uma conta, nunca um saldo guardado.** É o mesmo princípio do estoque (§4.1): número guardado envelhece, conta refeita não mente. Três fontes independentes — vendas, despesas e perdas — recalculadas a cada abertura da tela.
2. **A tarifa do ML já vem do relatório**, com o sinal dele. Não se digita comissão à mão: ela é o segundo maior custo da operação e erraria sempre.
3. **Linha sem custo é sinalizada, não escondida.** Produto que vendeu sem custo cadastrado infla o lucro; a tela diz quantas linhas estão assim, e a coluna de margem mostra `sem custo` em vez de um número bonito e falso.

Complementos da tela: lucro **por produto** (ordenado, para ver quem dá prejuízo) e exportação em CSV do período inteiro — demonstrativo, despesas e produtos — que é o arquivo que ela manda para o contador.

---

## 6. Diretrizes de interface

A usuária tem pouca familiaridade digital. Isso é **requisito**, não observação — cada item abaixo é verificável.

**Tela inicial: quatro botões grandes, com ícone e texto.**
`Ver estoque` · `Importar vendas` · `Entrada de mercadoria` · `Backup`
Acima deles, uma faixa de alertas: *"3 itens acabando — isso trava 5 kits"*.

**Regras:**

- **Sem jargão.** "SKU" → *Código do produto*. "Composição/BOM" → *"Este kit é montado com"*. "Movimento de estoque" → *Histórico*.
- **Fonte base 14pt**, alvos de clique de no mínimo 40px.
- **Uma busca só**, que procura em nome, código e código de barras ao mesmo tempo. Com 200 itens, filtro incremental em memória basta.
- **Cor com significado consistente**, sempre acompanhada de texto — não depender só da cor. A paleta é a do [manual da marca](../design-document.md) §03, que é **mono**: um vermelho só, sobre tinta e cinza. Então: vermelho `#B32309` = abaixo do mínimo, negativo ou pendente; cinza `#6F6863` = atenção e texto secundário; tinta `#201E1D` = normal e resultado positivo. **Não existe verde nem amarelo** — a distinção que antes era matiz agora é peso da letra (kit em 700, item em 400) e a régua de 2px da faixa. Isso é uma mudança em relação à primeira versão desta seção, e vale porque a regra “sempre acompanhado de texto” já estava valendo: nenhuma informação dependia do matiz para ser lida.
- **Tipografia Archivo**, nos pesos 400/600/700 do manual §04, empacotada com o app. Números de tabela sempre tabulares. Tudo alinhado à esquerda, inclusive cabeçalho de tabela e rótulo de formulário.
- **Kit nunca parece produto simples.** Ícone diferente, "dá para montar" em vez de quantidade, e campo de estoque bloqueado com a explicação *"O estoque do kit vem dos itens que o compõem."*
- **Toda ação destrutiva pede confirmação em português claro**, com número: *"Você vai dar baixa de 61 unidades em 22 produtos. Confirmar?"*
- **Desfazer sempre visível** depois de qualquer operação em lote.
- **Erro nunca é técnico.** Não *"KeyError: 'SKU'"*, e sim *"Este arquivo não parece ser o relatório de vendas do Mercado Livre. Baixe em Vendas → Exportar → Excel."* — com um botão *Copiar detalhes técnicos* para ele diagnosticar por telefone.
- **Nada de modal sem saída.** Toda janela tem *Cancelar*.
- **Feedback imediato** em qualquer operação acima de 300ms.
- **Salvamento automático.** Nunca "você esqueceu de salvar".

---

## 7. Backup

### 7.1 Local (v1)

- **Automático:** ao abrir e ao fechar o app, um CSV por tabela em `backups/AAAA-MM-DD_HHMM/`. Retenção: 30 dias, limpeza automática.
- **Manual:** botão *Backup agora* → escolhe a pasta, gera um `.zip` com os CSVs + cópia do `.db`.
- **Restaurar:** importa um backup, com confirmação forte e backup automático do estado atual antes.

> ⚠️ O CSV precisa incluir a tabela **`composicao`**. Um backup só de produtos e saldos perderia a informação que mais custou tempo para montar.

### 7.2 Google Drive (fase 2)

Duas rotas, e recomendo começar pela primeira:

**A) Pasta sincronizada — simples, zero configuração.**
Se o Google Drive para Desktop estiver instalado, o app detecta a pasta e oferece salvar o backup lá dentro. O Drive sincroniza sozinho. **Sem OAuth, sem token, sem nada para expirar.** Cobre o objetivo real (backup fora da máquina) com 1% do esforço.

**B) OAuth + API do Drive — a integração "de verdade".**
- Fluxo `InstalledAppFlow` (abre o navegador, volta para `localhost`).
- **Escopo `drive.file` apenas** — o app só enxerga arquivos que ele mesmo criou. Menos assustador na tela de permissão e, por não ser escopo sensível, **dispensa o processo de verificação do Google**.
- ⚠️ **Armadilha:** com o app OAuth em modo *Testing*, o refresh token **expira em 7 dias** e ela teria que reautorizar toda semana. É obrigatório publicar o app (*In production*) no Google Cloud Console. Com `drive.file` isso não exige auditoria.
- Token no `keyring` do SO, nunca em arquivo.
- Falha de rede **nunca** bloqueia o backup local.

---

## 8. Estrutura do projeto

```
inventory-tracker/
├── src/estoque_facil/
│   ├── __main__.py
│   ├── version.py              # fonte única da versão (semver)
│   ├── core/
│   │   ├── models.py           # SQLAlchemy
│   │   ├── repo.py
│   │   ├── ledger.py           # regras de movimento
│   │   ├── kits.py             # explosão e disponibilidade — §5.2
│   │   └── db.py
│   ├── importers/
│   │   ├── base.py
│   │   ├── ml_vendas_xlsx.py   # parser do §2
│   │   └── planilha_generica.py
│   ├── services/
│   │   ├── backup.py
│   │   ├── drive.py
│   │   └── updater.py
│   ├── ui/
│   │   ├── main_window.py
│   │   ├── marca.py            # tokens da marca: cor, tipografia, símbolo
│   │   ├── tema.py             # aplica fonte + QSS + ícone no QApplication
│   │   ├── tela_estoque.py
│   │   ├── tela_importacao.py  # tela de conferência do §5.1
│   │   ├── tela_produto.py     # inclui editor de composição
│   │   ├── widgets/
│   │   └── style.qss           # gerado a partir de marca.py (tokens @NOME@)
│   └── resources/
│       ├── fontes/             # Archivo variável (OFL) + licença
│       ├── marca/              # símbolo, lockups, ícones, setas do QSS
│       ├── icone.ico           # instalador e executável Windows
│       └── icone.icns          # bundle do macOS
├── alembic/
├── tests/
│   └── fixtures/               # XLSX reais anonimizados
├── packaging/
│   ├── estoque_facil.spec
│   ├── windows/installer.iss   # Inno Setup — plataforma principal
│   └── macos/build_dmg.sh
├── .github/workflows/release.yml
├── docs/ESCOPO.md              # este documento
├── proto/
│   ├── parser.py               # parser do relatório ML — validado
│   ├── kits.py                 # disponibilidade e explosão — validado
│   └── sugerir_composicao.py   # sugestão por nome + conferência de custo
└── pyproject.toml
```

**Regra de arquitetura:** `core/` e `importers/` **não importam nada de `ui/`**. Toda regra de negócio é testável sem abrir janela. É isso que torna o app confiável.

**Regra do sistema visual:** nenhum hex de cor e nenhum nome de fonte fora de `ui/marca.py`. O `style.qss` recebe os valores por substituição de token, e `tests/test_marca.py` falha se alguma cor escapar para dentro de uma tela.

---

## 9. Empacotamento e distribuição

**Windows é a plataforma principal** (máquina da operação). macOS é secundária — máquina de desenvolvimento do Guilherme. Isso define onde investir.

### 9.1 Build

**PyInstaller** em modo `onedir` (não `onefile`): abre bem mais rápido e o antivírus reclama menos.

- **Windows:** `.exe` + instalador **Inno Setup** (atalho na área de trabalho, menu iniciar, desinstalador). Testar manualmente a cada release.
- **macOS:** `.app` em `.dmg`. Build no CI, teste informal.

**CI:** GitHub Actions com matriz `windows-latest` + `macos-latest`. Tag `v*` → build → anexa artefatos + `SHA256SUMS` ao Release.

### 9.2 Assinatura

| Sistema | Sem assinar | Custo para resolver | Decisão |
|---|---|---|---|
| **Windows** | SmartScreen: "aplicativo não reconhecido" → *Mais informações → Executar assim mesmo* | Certificado EV ~US$ 300/ano | **Adiar.** Guia com prints resolve; a reputação melhora com o tempo. Reavaliar se ela se assustar. |
| **macOS** | Gatekeeper bloqueia → botão direito → *Abrir* na 1ª vez | Apple Developer US$ 99/ano | **Não pagar.** É a máquina do Guilherme, ele contorna sem problema. |

> 💡 **Detalhe importante e não óbvio:** arquivos baixados pelo *próprio app* (via `httpx`) **não recebem o atributo de quarentena** do macOS. O Gatekeeper só atrapalha **a primeira instalação** — todas as atualizações automáticas passam limpo.

---

## 10. Atualização automática

### 10.1 Como funciona

1. Ao abrir (e sob demanda em *Ajuda → Buscar atualizações*), consulta
   `GET https://api.github.com/repos/{owner}/inventory-tracker/releases/latest`.
2. Compara `tag_name` com `version.py` por **semver**.
3. Se houver versão nova: aviso **discreto e não bloqueante** (faixa no topo, nunca popup no meio do trabalho) com *O que mudou* vindo do corpo do Release.
4. Baixa o artefato da plataforma com barra de progresso.
5. **Verifica o SHA256** contra `SHA256SUMS` do Release. Não bateu, aborta.
6. Aplica:
   - **Windows:** executa o instalador em modo silencioso (`/VERYSILENT /NORESTART`) e fecha o app.
   - **macOS:** extrai para pasta temporária, substitui o `.app` com `ditto`, relança.
7. **Alembic roda as migrações na primeira abertura da versão nova**, sempre com backup automático antes.

### 10.2 Regras

- **Nunca atualizar sozinho sem avisar.** Sempre "Atualizar agora / Depois".
- **Nunca atualizar** com importação em andamento.
- Backup do banco antes de qualquer migração.
- Repositório **público** (ou um repo separado só para releases), senão o download exige token.
- Guardar a versão anterior por uma execução, para rollback manual.

**Alternativa considerada:** [`tufup`](https://github.com/dennisvang/tufup) — atualização assinada baseada em TUF, mais seguro porém bem mais complexo. **Recomendo o esquema acima com SHA256**, e migrar para `tufup` se o app um dia sair da família.

---

## 11. Testes e qualidade

Prioridade nos testes que impedem perda de dados:

1. **Invariante do livro-razão** — para qualquer sequência de operações, `soma(movimentos) == saldo`. O teste mais importante do projeto.
2. **Disponibilidade de kit** — `min(saldo ÷ qtd)`; componente compartilhado entre kits; componente zerado zera todos os kits que dependem dele; quantidade > 1 por componente.
3. **Explosão de kit na importação** — vender 2 kits que compartilham componente baixa a soma correta; venda mista (kit + avulso do mesmo componente) na mesma importação.
4. **Idempotência** — importar o mesmo arquivo 2× produz exatamente os mesmos saldos, **incluindo vendas de kit** (que geram vários movimentos com a mesma referência — o caso mais fácil de quebrar). Vale também para o dinheiro: o balanço não pode dobrar na reimportação.
5. **Parser do ML** — fixtures com XLSX reais anonimizados: normal, com devolução, com cancelamento, com SKU vazio, com venda Full, coluna faltando, arquivo errado (relatório de tarifas).
6. **Desfazer lote** — restaura o estado exato anterior, componentes incluídos.
7. **Composição inválida** — ciclo, kit dentro de kit, quantidade zero → todos recusados.
8. **Migrações** — banco da v1.0 migra para a v1.1 sem perda.
9. **Smoke de empacotamento** — o CI abre o app buildado e fecha, para pegar dependência faltando no bundle.

Ferramentas: `pytest`, `ruff`, `mypy` no `core/`. CI em cada PR.

---

## 12. Roadmap

### Fase 1 — MVP
- [ ] Setup: repo, `pyproject`, ruff, pytest, CI
- [ ] Modelo de dados + Alembic + livro-razão
- [ ] **Kits: composição, disponibilidade calculada, explosão na venda** (§5.2)
- [ ] CRUD de produtos + cadastro rápido + editor de composição
- [ ] **Importador do XLSX do ML** com tela de conferência (§5.1)
- [ ] Classificação casa × Full por `Forma de entrega` (§2.5)
- [ ] Cadastro automático a partir do relatório, com sugestão de kits (§2.8)
- [ ] **Carga inicial em 3 passos** (§5.3): CSV de custos → nomes via relatório ML → marcar kits
- [ ] **Transformar item em kit** + tela "Kits sem composição" + sugestão por nome (§5.2.1–5.2.2)
- [ ] Importação de composições por planilha (`kit;componente;qtd`)
- [ ] Tela de estoque: busca, filtro simples/kits, alerta em cascata
- [ ] Entrada de mercadoria
- [ ] Backup CSV automático e manual
- [ ] Empacotamento Windows (principal) + macOS

### Fase 2 — Conforto
- [ ] Auto-atualização via GitHub Releases
- [ ] Backup no Google Drive (rota A, depois B)
- [ ] Inventário/contagem física
- [ ] Histórico por produto, mostrando por qual kit saiu
- [ ] Devoluções pelo relatório
- [ ] Relatório de reposição priorizado por kits destravados
- [ ] Transferência para o Full

### Fase 3 — Fechar o ciclo
- [ ] **API oficial do Mercado Livre — atualizar o estoque dos anúncios afetados** (§5.2). É o objetivo final: hoje o ML não sabe que vender um kit reduz o avulso.
- [x] Margem por produto (preço − custo − tarifas do relatório) — entregue na §5.8
- [ ] Mais vendidos / curva ABC / giro
- [ ] Previsão de ruptura ("acaba em ~6 dias")
- [ ] Etiquetas de código de barras
- [ ] Leitor de código de barras USB

---

## 13. Questões em aberto

Respondidas: Full × casa (casa é o principal) · kits montados na hora (v1) · Windows é a máquina principal · 195 SKUs, 75 kits · única fonte de dados é o CSV de custos, **sem composições** — elas serão cadastradas no app (§5.2.1).

Ainda em aberto:

1. **Quantos componentes tem um kit típico?** 2–3 ou chega a 5–6? Define se o editor de composição cabe na tela do produto ou precisa de janela própria. Dá para responder olhando 5 anúncios.
2. **Embalagem/sacola/laço entram como componente?** Se sim, o "dá para montar" fica correto de verdade, mas o cadastro fica mais chato e o catálogo cresce. Sugiro **não** na v1 — e reavaliar se ela ficar sem embalagem alguma vez.
3. **O custo do CSV está atualizado?** Ele vira a base da conferência da §5.2.3 e, na fase 3, do cálculo de margem. Se estiver velho, o aviso de divergência vira ruído e é melhor desligá-lo.
4. **Precisa acompanhar margem**, ou só quantidade? O custo já está no CSV, então margem sai quase de graça — mas só vale a tela se ela for usar.
5. **Dá para exportar um relatório de vendas de 90 dias?** É o que preenche os nomes dos produtos (§5.3 passo 2). Quanto maior o período, menos digitação.

---

## 14. Riscos

| Risco | Impacto | Mitigação |
|---|---|---|
| **Composição errada de kit** | **Alto** | É o novo risco nº 1: um erro na composição erra o estoque de vários produtos ao mesmo tempo. Mitigar com: preview antes de salvar, "dá para montar" sempre visível para conferência, e histórico que mostra por qual kit o item saiu |
| **Cadastrar as composições dos 75 kits** | **Alto** | É o maior custo de entrada do projeto (~225 linhas). Mitigar com os três recursos da §5.2: sugestão por nome, tela de lote com contador, e importação por planilha. **Não deixar isso só na digitação item a item** |
| Catálogo sem nome de produto | Médio | Relatório ML de 90 dias preenche a maioria (§5.3 passo 2); o resto fica como pendência leve |
| Falso positivo na detecção de kit | Baixo | Ela confirma em lote; converter de volta para simples é permitido (§5.2.1) |
| Estoque do anúncio no ML desatualizado | Alto | v1 destaca divergências; fase 3 resolve via API |
| ML muda o layout do relatório | Alto | Detecção do cabeçalho por texto (§2.1); mapeamento manual de colunas como escape |
| Baixa duplicada | Alto | Índice único incluindo `produto_id` (§4.3) — impossível por construção |
| Corrupção do SQLite | Alto | WAL + backup automático a cada abertura/fechamento |
| SmartScreen assusta a usuária | Médio | Guia com prints; certificado EV se necessário |
| Ela abandona por achar complicado | Médio | §6 é requisito; kits são o conceito mais difícil — testar essa tela com ela na primeira semana |
| Atualização quebra o banco | Médio | Backup obrigatório antes da migração; teste de migração no CI |

---

## 15. Próximos passos sugeridos

1. **Exportar um relatório de vendas de 90 dias** do ML e me mandar. É o que dá nome aos 195 produtos — sem custo nenhum, e evita um catálogo só de códigos.
2. Fechar o esqueleto do projeto e o modelo de dados, com `composicao` desde o primeiro commit.
3. Implementar **`core/kits.py` e `core/ledger.py` com testes primeiro** — disponibilidade e explosão de kit. São as peças de maior risco e maior valor.
4. Depois o **parser do ML**, aproveitando `proto/parser.py`.
5. Construir **cedo** a tela de composição (§5.2.1), mesmo feia. Os 75 kits são o caminho crítico: quanto antes ela começar a cadastrar, antes o app fica utilizável — e o cadastro pode acontecer em paralelo ao resto do desenvolvimento.
6. Só então o restante da interface.

---

## Anexo A — Validação do parser contra o arquivo real

As regras da §2 foram implementadas em protótipo (`proto/parser.py`) e executadas contra
`20260821_Vendas_BR_Mercado_Libre_y_Mercado_Shops_...xlsx`:

```
linhas lidas ......................... 51
período coberto ...................... 12/08/2026 a 21/08/2026   (8 dias — confirma §2.3)
datas não interpretadas .............. 0                          (parser pt-BR ok)
linhas sem SKU ....................... 0                          (SKU é chave confiável)
N.º de venda únicos .................. 51                          (1 linha = 1 venda)
forma de entrega ..................... 'Correios e pontos de envio' 51/51   → CASA (§2.5)
depósito ............................. 'Carapicuíba Alameda dos Babaçu'     (depósito dela)
devoluções / cancelamentos ........... 0 / 0
unidades vendidas .................... 57
produtos distintos ................... 16

reimportação do mesmo arquivo ........ 0 vendas novas   ✅ idempotência confirmada
```

**Vendas do período, por SKU:**

| Qtd | SKU | Provável tipo |
|---:|---|---|
| 13 | kit.maope.rosa | **kit** |
| 11 | pamperspants.g28 | simples |
| 10 | pamperspants.p | simples |
| 4 | pamperspants.m | simples |
| 3 | pamperspants.m30 | simples |
| 2 | pano.boca.prendedorchupeta.rosa | **kit** |
| 2 | pompom.m28 | simples |
| 2 | kit.travesseirosazul | **kit** |
| 2 | livro.animaisdomar | **kit** |
| 2 | kit.maope.azul | **kit** |
| 1 | caixahuggies.lenço | **kit** |
| 1 | cobertor.capuz.coelha | simples |
| 1 | pamperspantsm+lenço | **kit** |
| 1 | kit.livros.4amigosdomar | **kit** |
| 1 | fralda.pano.planetas | **kit** |
| 1 | mord.mao.azul | simples |

Observações:

- **9 dos 16 SKUs são kits** — mais da metade do catálogo movimentado. Confirma a promoção da §5.2 para a v1.
- **`mord.mao.azul` vende sozinho e é componente do `kit.maope.azul`.** O caso de estoque compartilhado aparece já numa amostra de 8 dias — não é hipótese.
- **`KIT.MAOPE.ROSA` é 25% das vendas.** Se a composição dele estiver errada, um quarto do estoque fica errado.
- **Fraldas Pampers Pants somam 28 das 57 unidades** em 4 tamanhos — o grupo que mais precisa de alerta de mínimo e previsão de ruptura.
- A coluna "Provável tipo" acima é exatamente a heurística sugerida na §2.8 (SKU/título começando com "kit", ou contendo "+"). Acertaria a triagem inicial — mas ela precisa confirmar item a item.

---

## Anexo B — Análise do catálogo (`atributosprodutos.csv`)

### B.1 O arquivo

| | |
|---|---|
| Formato | CSV, separador `;`, decimal `.`, UTF-8 (acentos ok: `lenço`, `pescoço`) |
| Colunas | `CUSTO`, `IMPOSTO`, `SKU` — **não há nome de produto** |
| Registros | 195 SKUs, **nenhum duplicado** |
| Custos | de R$ 3,34 (`travesseiro.furo.rosa`) a R$ 174,72 (`KIT.ENXMAT.ROSA`) |
| Imposto | dois valores apenas: `4.72` (129 itens) e `4.40` (66) — provavelmente alíquota % |
| Kits (heurística) | **75** contêm `kit` ou `+` no SKU — 38% do catálogo |
| Cruzamento com o relatório de vendas | os 16 SKUs vendidos estão todos no CSV ✅ — o CSV é a fonte completa |

### B.2 Tentativa de inferir as composições automaticamente — **não funciona**

A hipótese era atraente e chegou a se confirmar nos primeiros testes:

```
KIT.MAOPE.ROSA (R$ 13,50) = mord.mao.rosa (6,75) + mord.pe.rosa (6,75)  ✅ exato
KIT.MAOPE.AZUL (R$ 13,50) = mord.mao.azul (6,75) + mord.pe.azul (6,75)  ✅ exato
```

Se o custo do kit é a soma dos componentes, bastaria resolver um subset-sum para descobrir todas as composições e poupar horas de cadastro. **Implementei e medi. A conclusão é que não dá.**

**Por quê:** os custos colidem demais.

```
98 custos distintos para 195 SKUs
59 valores de custo são compartilhados por 2 ou mais SKUs (cobrindo 156 dos 195)

   R$  8,00 → 7 SKUs   (livrobanho.mundobita, livro.louvandosenhor, livrobanho.alfabeto, ...)
   R$ 11,90 → 5 SKUs   (manta.rosa, manta.laranja, manta.bege, manta.azul, manta.pink)
   R$ 14,50 → 5 SKUs   (NANINHA.UNIC, NANINHA.GIRAFA, NANINHA.GAT, NANINHA.URSO, ...)
```

O caso que mata a ideia é justamente o kit mais vendido:
**`mord.mao.rosa` e `mord.pe.rosa` custam os dois R$ 6,75.** Então `mão + pé` e `2× mão` somam ambos R$ 13,50 — e o custo, sozinho, não distingue. De fato, o algoritmo sugeriu `2x mord.mao.rosa` para o `KIT.MAOPE.ROSA`, que é o kit responsável por 25% das vendas.

Na medição completa, cada kit teve entre 13 e 246 combinações de custo válidas. Mesmo ranqueando por semelhança de nome, os "melhores" resultados incluíam absurdos como `KIT.HORADOBANHOAZUL = 5x manta.azul`.

> **Conclusão registrada para não ser tentada de novo:** inferir composição a partir de custo produz sugestões erradas com aparência de certeza — o pior tipo de erro num app cujo propósito é dar confiança no número. **Descartado.**

### B.3 O que fazer com o custo, então: conferir

O mesmo dado funciona muito bem **depois** que ela monta a composição:

```
composição informada: mord.mao.rosa + mord.pe.rosa  →  R$ 13,50 = custo do kit    ✅ bate
composição informada: mord.mao.rosa                 →  R$  6,75, faltam R$ 6,75   ⚠️ falta item?
```

Verificar é fácil onde adivinhar é impossível. Vira o aviso da §5.2.3 — que pega composição incompleta sem nunca bloquear.

### B.4 O que funciona de verdade: sugerir por nome

Os SKUs são descritivos, e casar seus pedaços contra os SKUs simples coloca os componentes certos no topo:

| Kit | Sugestões (ordenadas) |
|---|---|
| `kit.mantamordedorazul` | **mord.pe.azul** (100%), **manta.azul** (100%), **mord.mao.azul** (67%), manta.karinho.azul (67%) |
| `kit.naninha.manta.girafa` | **NANINHA.GIRAFA** (100%), manta.rosa (50%), manta.pink (50%), manta.laranja (50%) |
| `KIT.CUEIROPAMPERSROSA` | **cueiro.rosa** (100%), pamperspants.P (100%), pamperspants.M (100%), pamperspants.G (100%) |
| `KIT.MAOPE.ROSA` | **mord.mao.rosa** (67%), **mord.pe.rosa** (50%), manta.rosa (50%) |

Não decide sozinho — em `KIT.CUEIROPAMPERSROSA` ela ainda escolhe o tamanho da fralda, e é ela quem sabe. Mas troca "procurar entre 120 itens" por "clicar em dois", 75 vezes. É esse ganho que vai para a §5.2.2.

Protótipo em `proto/sugerir_composicao.py`.
