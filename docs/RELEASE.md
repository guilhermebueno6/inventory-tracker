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

> Não crie o Release pela interface do GitHub ("Draft a new release"). Ela marca
> a tag e publica o Release na hora, **vazio**; o workflow só anexa os arquivos
> quando termina de compilar. Se falhar, o Release fica lá sem nada para baixar.

## 3b. O Release saiu sem os executáveis

Aconteceu na v0.3: o build falhou e o Release ficou só com as notas, sem `.exe`
nem `.dmg`. Não precisa apagar a tag nem publicar outra versão — dá para
recompilar a mesma tag e anexar os arquivos ao Release que já está lá:

```bash
gh workflow run release.yml --ref main -f tag=v0.3
```

O workflow compila o código **da tag** informada e anexa os arquivos, sem mexer
no texto do Release. Pela interface: aba **Actions → release → Run workflow**,
preenchendo a tag.

Antes de rodar, veja por que o build caiu:

```bash
gh run list --workflow=release.yml --limit 5
gh run view <id> --log-failed
```

Se o motivo estiver no código (e não no CI), corrija na `main` primeiro e mova a
tag para o commit corrigido — senão o rebuild vai falhar igual.

## 4. Confira

O app instalado busca a versão nova na próxima abertura. Para testar sem esperar:
**Ajuda → Buscar atualizações**.

Se a tag foi publicada mas o app não enxerga:

- o `GITHUB_REPO` em `version.py` aponta para o repositório certo?
- o repositório é público? (privado exigiria token embutido — má ideia)
- o Release tem os arquivos `.exe`/`.dmg` **e** o `SHA256SUMS`? (se não tem,
  veja a seção 3b — sem instalador o app não oferece atualização nenhuma)

## Se uma atualização der errado

O banco anterior está em `backups/antes-de-atualizar/`, dentro da pasta de dados
(**Ajuda → Onde ficam meus dados**). Feche o app, troque o `estoque.db` pela
cópia e reinstale a versão anterior a partir dos Releases do GitHub.
