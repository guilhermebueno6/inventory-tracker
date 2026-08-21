# Como publicar uma versão

## 1. Mudou o modelo de dados?

Se você acrescentou, removeu ou alterou uma coluna em `core/models.py`, o banco
instalado na máquina dela precisa saber como se transformar. Sem migração, o app
novo abre o banco antigo e quebra.

```bash
cd inventory-tracker
source .venv/bin/activate

# gera a migração comparando o modelo com um banco na revisão atual
python - <<'PY'
from alembic.config import Config
from alembic import command
cfg = Config()
cfg.set_main_option("script_location", "src/estoque_facil/migracoes")
cfg.set_main_option("sqlalchemy.url", "sqlite:////tmp/gerar.db")
command.upgrade(cfg, "head")          # põe o banco temporário em dia
command.revision(cfg, message="descricao curta", autogenerate=True)
PY
```

Abra o arquivo gerado em `src/estoque_facil/migracoes/versions/` e **torne-o
defensivo** — veja `0002_fornecedor_no_produto.py`:

```python
def _tem_coluna(tabela, coluna):
    inspetor = sa.inspect(op.get_bind())
    return coluna in {c["name"] for c in inspetor.get_columns(tabela)}

def upgrade():
    if _tem_coluna("produto", "fornecedor"):
        return
    ...
```

Motivo: as primeiras instalações criaram o banco sem controle de versão e são
adotadas como revisão `0001`. Se o schema real estiver adiantado, uma migração
cega falha e o "conserto" óbvio é apagar o banco — perdendo o estoque.

Rode os testes: `pytest tests/test_migracoes.py -q`. Eles simulam exatamente a
atualização, com dados dentro.

## 2. Suba a versão

Em `src/estoque_facil/version.py`, ajuste `__version__` seguindo semver.

## 3. Marque e publique

```bash
git add -A && git commit -m "v0.2.0: descrição"
git tag v0.2.0
git push origin main --tags
```

O workflow `release.yml` compila nas duas plataformas, calcula o `SHA256SUMS` e
cria o Release. Leva alguns minutos.

## 4. Confira

O app instalado busca a versão nova na próxima abertura. Para testar sem esperar:
**Ajuda → Buscar atualizações**.

Se a tag foi publicada mas o app não enxerga:

- o `GITHUB_REPO` em `version.py` aponta para o repositório certo?
- o repositório é público? (privado exigiria token embutido — má ideia)
- o Release tem os arquivos `.exe`/`.dmg` **e** o `SHA256SUMS`?

## Se uma atualização der errado

O banco anterior está em `backups/antes-de-atualizar/`, dentro da pasta de dados
(**Ajuda → Onde ficam meus dados**). Feche o app, troque o `estoque.db` pela
cópia e reinstale a versão anterior a partir dos Releases do GitHub.
