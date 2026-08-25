"""Comparação de versões do updater — ESCOPO.md §10."""
from estoque_facil.services.updater import ha_versao_nova


def test_compara_versoes_por_semver_nao_por_texto():
    assert ha_versao_nova("0.1.0", "0.2.0")
    assert ha_versao_nova("0.9.0", "0.10.0"), "texto diria que 0.10 < 0.9"
    assert ha_versao_nova("1.0.0", "1.0.1")
    assert not ha_versao_nova("1.2.0", "1.2.0")
    assert not ha_versao_nova("2.0.0", "1.9.9")


def test_aceita_tag_com_v():
    assert ha_versao_nova("0.1.0", "v0.2.0")


def test_repositorio_configurado():
    """Se isto ficar errado, o botão de atualizar procura no lugar errado."""
    from estoque_facil.version import GITHUB_REPO

    dono, _, nome = GITHUB_REPO.partition("/")
    assert dono and nome, "GITHUB_REPO precisa ser 'usuario/repositorio'"
    assert "seu-usuario" not in GITHUB_REPO and "exemplo" not in GITHUB_REPO


def test_versao_e_semver():
    from estoque_facil.version import __version__

    partes = __version__.split(".")
    assert len(partes) == 3 and all(p.isdigit() for p in partes)


def test_migracoes_acompanham_a_versao():
    """Toda versão publicada precisa ter uma revisão de banco correspondente."""
    from estoque_facil.core.migracoes import revisao_do_codigo

    assert revisao_do_codigo() is not None, "sem migração, o banco não evolui"


def test_tag_curta_e_a_mesma_versao():
    """A v0.3 foi marcada como `v0.3` com o version.py em `0.3.0`.

    As duas são a mesma versão: quem já está na 0.3.0 não pode receber oferta
    de atualização, e o release.yml não pode recusar a tag por isso.
    """
    assert not ha_versao_nova("0.3.0", "v0.3")
    assert not ha_versao_nova("0.3", "v0.3.0")
    assert ha_versao_nova("0.2.1", "v0.3")
    assert ha_versao_nova("0.3", "v0.3.1")


def test_release_sem_executavel_nao_vira_atualizacao():
    """Foi o caso da v0.3: Release publicado, mas com zero arquivos.

    Sem instalador não há o que baixar — o app precisa ficar quieto em vez de
    tentar atualizar para o nada.
    """
    import httpx

    from estoque_facil.services import updater

    resposta = httpx.Response(
        200,
        json={"tag_name": "v0.9.0", "body": "notas", "assets": []},
        request=httpx.Request("GET", "https://api.github.com/"),
    )
    original = httpx.get
    httpx.get = lambda *a, **k: resposta
    try:
        assert updater.verificar(repo="x/y", atual="0.3.0") is None
    finally:
        httpx.get = original
