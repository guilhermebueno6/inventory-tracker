# Estoque Fácil

Controle de estoque para a loja do Mercado Livre. Aplicativo desktop (Windows e macOS)
feito em Python, pensado para ser usado por quem não tem familiaridade com computador.

O escopo completo, com as decisões e o porquê de cada uma, está em
[`docs/ESCOPO.md`](docs/ESCOPO.md).

## O que ele resolve

1. **Saber quanto tem de cada produto**, sem planilha manual.
2. **Dar baixa das vendas** importando o relatório que o Mercado Livre já gera.
3. **Kits que compartilham componentes** — o problema que planilha nenhuma resolve.
4. **Não perder os dados**, com backup automático em CSV.

### A ideia central: kit não tem estoque

Os kits são montados na hora do envio, então o que existe na prateleira são os
componentes. O app calcula:

```
disponível(kit) = min( estoque(componente) ÷ quantidade necessária )
```

Assim, quando o mordedor-pé rosa acaba, o app sabe **sozinho** que o `KIT.MAOPE.ROSA`
foi a zero — e diz quais outros kits aquele item trava.

## Rodando em modo de desenvolvimento

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python -m estoque_facil
```

Testes:

```bash
pytest -q                      # 66 testes
QT_QPA_PLATFORM=offscreen pytest -q   # em servidor sem tela
ruff check src tests
```

## Primeiro uso

1. **Arquivo → Importar catálogo (CSV)** — o arquivo `CUSTO;IMPOSTO;SKU`.
   Cria os produtos e marca como kit os que têm `kit` ou `+` no código.
2. **Arquivo → Preencher nomes pelo relatório do ML** — dá nome aos produtos.
   Quanto maior o período do relatório, mais produtos ficam com nome.
3. **Configurar kits que faltam** — para cada kit, escolha de que ele é montado.
   As sugestões já vêm ordenadas por semelhança de nome.
4. **Importar vendas** — arraste o relatório do ML. Confira e confirme.

> A ordem importa: se importar vendas com kits ainda sem composição, essas linhas
> ficam pendentes e o trabalho precisa ser refeito.

## Atualizar sem perder o estoque

Esta é a garantia mais importante do projeto, e ela tem três camadas.

**1. Os dados moram fora do programa.** O banco fica em `%LOCALAPPDATA%\EstoqueFacil\`
(Windows) ou `~/Library/Application Support/EstoqueFacil/` (macOS), nunca junto do
executável. Desinstalar, reinstalar ou trocar de versão não encosta nele.
No app: **Ajuda → Onde ficam meus dados**.

**2. O banco evolui, não é recriado.** Cada versão traz suas migrações (Alembic), que
transformam o banco antigo no formato novo preservando o conteúdo. Isso existe por um
motivo concreto: `create_all()` cria tabelas que faltam mas **não altera as que já
existem** — uma versão com uma coluna a mais quebraria o banco instalado com
"no such column", e o conserto óbvio seria apagá-lo.

**3. Backup automático antes de migrar.** Toda migração começa copiando o banco para
`backups/antes-de-atualizar/`. A cópia usa a API de backup do SQLite, e não `shutil.copy`:
em modo WAL as escritas recentes ficam no arquivo `.db-wal`, e copiar só o `.db` produz
um backup vazio — aqui o `.db` tinha 4 KB contra 424 KB do WAL.

### Publicar uma versão nova

```bash
# 1. mexeu no modelo de dados? gere a migração
alembic -c /dev/null revision --autogenerate -m "descrição"   # veja docs/RELEASE.md

# 2. suba a versão em src/estoque_facil/version.py
# 3. marque e publique
git tag v0.2.0 && git push --tags
```

O GitHub Actions compila Windows e macOS, gera o `SHA256SUMS` e cria o Release.
O app instalado enxerga a versão nova na abertura, mostra uma faixa discreta no topo
(nunca um popup no meio do trabalho) e só atualiza se ela clicar. O instalador baixado
é conferido pelo SHA256 antes de rodar — se não bater, a atualização é abortada.

> **Regra ao escrever migrações:** deixe-as defensivas (verifique antes de aplicar).
> As primeiras instalações criaram o banco sem controle de versão e são "adotadas"
> como revisão `0001`; se o schema real já estiver adiantado, uma migração cega
> quebraria a atualização. Ver `0002_fornecedor_no_produto.py` como exemplo.

## Onde ficam os dados

Nunca ao lado do programa — em Windows, `Program Files` é somente leitura.

| Sistema | Pasta |
|---|---|
| Windows | `%LOCALAPPDATA%\EstoqueFacil\` |
| macOS | `~/Library/Application Support/EstoqueFacil/` |

```
estoque.db                    banco SQLite
backups/                      CSV automáticos (abertura e fechamento), 30 dias
backups/antes-de-atualizar/   cópia do banco antes de cada migração
importados/                   cópia dos relatórios processados
logs/app.log
```

A variável `ESTOQUE_FACIL_DIR` troca essa pasta — útil para testes ou pen drive.

## Estrutura

```
src/estoque_facil/
├── core/          regra de negócio, sem nada de interface
│   ├── models.py    tabelas
│   ├── ledger.py    livro-razão: todo movimento passa por aqui
│   ├── kits.py      disponibilidade, explosão, cascata
│   └── db.py        SQLite (WAL), caminhos por SO
├── importers/     leitura de arquivos externos
├── services/      importação, backup, sugestão, updater
└── ui/            PySide6
```

**Regra:** `core/` e `importers/` não importam nada de `ui/`. Toda a regra de
negócio é testável sem abrir janela.

## Duas decisões que valem saber

**Deduplicação por N.º de venda, não por arquivo.** O relatório do ML cobre vários
dias e se sobrepõe entre exportações. Como cada venda já processada fica gravada,
importar o mesmo arquivo duas vezes não faz nada — é seguro por construção. Isso
é garantido por um índice único no banco, não por código.

**Classificação casa × Full pela coluna `Forma de entrega`,** nunca pelo nome do
depósito, que é texto livre.

## Empacotar

```bash
pyinstaller packaging/estoque_facil.spec --noconfirm
# Windows: iscc packaging\windows\installer.iss
# macOS:   bash packaging/macos/build_dmg.sh
```

Publicar uma versão: `git tag v0.2.0 && git push --tags`. O GitHub Actions compila
nas duas plataformas, gera o `SHA256SUMS` e cria o Release — que é de onde o app
busca as atualizações.

Na primeira instalação o Windows mostra "aplicativo não reconhecido"
(*Mais informações → Executar assim mesmo*) e o macOS exige botão direito → *Abrir*.
Isso é esperado enquanto não houver certificado de assinatura.
