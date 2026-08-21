"""Fluxo de atualização — ESCOPO.md §10. Sem rede: tudo dublado."""
import hashlib
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from estoque_facil.services import updater  # noqa: E402


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


def _fake(versao="9.9.9", sha=None):
    return updater.Atualizacao(
        versao=versao, notas="Correções", url="https://exemplo/EstoqueFacil.exe",
        nome="EstoqueFacil.exe", sha256=sha,
    )


def test_download_recusa_arquivo_adulterado(monkeypatch, tmp_path):
    """Se o SHA256 não bate, a atualização é abortada — §10.1 passo 5."""
    conteudo = b"instalador falsificado"
    sha_certo = hashlib.sha256(b"instalador de verdade").hexdigest()

    class RespostaFalsa:
        headers = {"content-length": str(len(conteudo))}

        def raise_for_status(self):
            pass

        def iter_bytes(self, _n=0):
            yield conteudo

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr("httpx.stream", lambda *a, **k: RespostaFalsa())
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))

    with pytest.raises(RuntimeError, match="não confere"):
        updater.baixar(_fake(sha=sha_certo))

    assert not (tmp_path / "EstoqueFacil.exe").exists(), "arquivo suspeito não pode ficar"


def test_download_aceita_arquivo_integro(monkeypatch, tmp_path):
    conteudo = b"instalador de verdade"
    sha = hashlib.sha256(conteudo).hexdigest()

    class RespostaOk:
        headers = {"content-length": str(len(conteudo))}

        def raise_for_status(self):
            pass

        def iter_bytes(self, _n=0):
            yield conteudo

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr("httpx.stream", lambda *a, **k: RespostaOk())
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    caminho = updater.baixar(_fake(sha=sha))
    assert caminho.read_bytes() == conteudo


def test_sem_internet_nao_e_erro(monkeypatch):
    """Sem rede o app fica quieto — atualizar não é obrigação."""
    def explode(*a, **k):
        raise OSError("sem rede")

    monkeypatch.setattr("httpx.get", explode)
    assert updater.verificar(repo="x/y", atual="0.1.0") is None


def test_ignora_release_sem_arquivo_da_plataforma(monkeypatch):
    resposta = SimpleNamespace(
        json=lambda: {"tag_name": "v9.9.9", "body": "", "assets": [
            {"name": "codigo-fonte.zip", "browser_download_url": "http://x"},
        ]},
        raise_for_status=lambda: None,
    )
    monkeypatch.setattr("httpx.get", lambda *a, **k: resposta)
    assert updater.verificar(repo="x/y", atual="0.1.0") is None


def test_faixa_de_atualizacao_aparece_sem_bloquear(app, session):
    from estoque_facil.ui.main_window import JanelaPrincipal

    j = JanelaPrincipal(session)
    # isHidden e não isVisible: a janela não é mostrada no teste, e isVisible()
    # depende de todos os ancestrais estarem visíveis
    assert j.inicial.barra_atualizacao.isHidden(), "sem versão nova, nada aparece"

    j._resultado_atualizacao(_fake("0.2.0"), manual=False)
    assert not j.inicial.barra_atualizacao.isHidden()
    assert "0.2.0" in j.inicial.lb_atualizacao.text()
    assert j._atualizacao_pendente is not None


def test_nao_atualiza_no_meio_de_uma_importacao(app, session, monkeypatch):
    from estoque_facil.ui import main_window

    chamou = []
    monkeypatch.setattr(main_window, "informar", lambda *a, **k: chamou.append(a))
    monkeypatch.setattr(
        main_window, "DialogoAtualizacao",
        lambda *a, **k: pytest.fail("não pode abrir durante importação"),
    )

    j = main_window.JanelaPrincipal(session)
    j._atualizacao_pendente = _fake()
    j.importando = True
    j.abrir_atualizacao()
    assert chamou, "precisa avisar em vez de abrir"
    assert "importação" in chamou[0][2].lower()
