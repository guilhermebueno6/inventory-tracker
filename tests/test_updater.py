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
