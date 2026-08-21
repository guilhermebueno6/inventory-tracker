"""Atualização automática via GitHub Releases — ESCOPO.md §10.

Regras que este módulo respeita:
  • nunca atualiza sozinho sem avisar;
  • verifica o SHA256 antes de aplicar — não bateu, aborta;
  • backup do banco antes de qualquer migração (feito por quem chama).

Detalhe do macOS que vale saber: arquivos baixados pelo PRÓPRIO app (httpx) não
recebem o atributo de quarentena, então o Gatekeeper só atrapalha a primeira
instalação — as atualizações passam limpo.
"""
from __future__ import annotations

import hashlib
import platform
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ..version import GITHUB_REPO, __version__

API = "https://api.github.com/repos/{repo}/releases/latest"
TEMPO_LIMITE = 15.0


def _versao_tupla(texto: str) -> tuple[int, ...]:
    numeros = re.findall(r"\d+", texto or "")
    return tuple(int(n) for n in numeros[:3]) or (0,)


def ha_versao_nova(atual: str, remota: str) -> bool:
    return _versao_tupla(remota) > _versao_tupla(atual)


def _sufixo_plataforma() -> str:
    if sys.platform.startswith("win"):
        return ".exe"
    if sys.platform == "darwin":
        return ".dmg"
    return ".tar.gz"


@dataclass
class Atualizacao:
    versao: str
    notas: str
    url: str
    nome: str
    sha256: str | None = None


def verificar(repo: str = GITHUB_REPO, atual: str = __version__) -> Atualizacao | None:
    """Consulta o GitHub. Devolve None se já está na última versão ou se falhou."""
    import httpx

    try:
        r = httpx.get(API.format(repo=repo), timeout=TEMPO_LIMITE,
                      headers={"Accept": "application/vnd.github+json"})
        r.raise_for_status()
        dados = r.json()
    except Exception:  # noqa: BLE001 — sem internet não é erro, é silêncio
        return None

    tag = (dados.get("tag_name") or "").lstrip("vV")
    if not tag or not ha_versao_nova(atual, tag):
        return None

    sufixo = _sufixo_plataforma()
    ativos = dados.get("assets") or []
    alvo = next((a for a in ativos if (a.get("name") or "").endswith(sufixo)), None)
    if alvo is None:
        return None

    sha = None
    somas = next((a for a in ativos if (a.get("name") or "") == "SHA256SUMS"), None)
    if somas:
        try:
            texto = httpx.get(somas["browser_download_url"], timeout=TEMPO_LIMITE,
                              follow_redirects=True).text
            for linha in texto.splitlines():
                partes = linha.split()
                if len(partes) == 2 and partes[1].lstrip("*") == alvo["name"]:
                    sha = partes[0]
                    break
        except Exception:  # noqa: BLE001
            sha = None

    return Atualizacao(
        versao=tag,
        notas=(dados.get("body") or "").strip(),
        url=alvo["browser_download_url"],
        nome=alvo["name"],
        sha256=sha,
    )


def baixar(atualizacao: Atualizacao, progresso=None) -> Path:
    """Baixa e confere o SHA256. Levanta erro se não bater."""
    import httpx

    destino = Path(tempfile.gettempdir()) / atualizacao.nome
    digest = hashlib.sha256()
    with httpx.stream("GET", atualizacao.url, timeout=None, follow_redirects=True) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length") or 0)
        baixado = 0
        with open(destino, "wb") as fh:
            for bloco in r.iter_bytes(65536):
                fh.write(bloco)
                digest.update(bloco)
                baixado += len(bloco)
                if progresso and total:
                    progresso(baixado / total)

    if atualizacao.sha256 and digest.hexdigest().lower() != atualizacao.sha256.lower():
        destino.unlink(missing_ok=True)
        raise RuntimeError(
            "O arquivo baixado não confere com o esperado. "
            "A atualização foi cancelada por segurança."
        )
    return destino


def aplicar(arquivo: Path) -> None:
    """Executa a atualização e encerra o app. Windows: instalador silencioso."""
    arquivo = Path(arquivo)
    if sys.platform.startswith("win"):
        subprocess.Popen([str(arquivo), "/VERYSILENT", "/NORESTART"], close_fds=True)
        sys.exit(0)
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(arquivo)], close_fds=True)
        sys.exit(0)
    raise RuntimeError(
        f"Atualização automática não disponível em {platform.system()}. "
        f"Baixe manualmente: {arquivo}"
    )
