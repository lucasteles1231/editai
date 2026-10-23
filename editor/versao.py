"""
As versões publicadas e o aviso de versão nova (a escolha do dono, 23/10/2026).

**O aviso:** uma vez por dia, o Editai pergunta ao GitHub qual é a última versão publicada.
Se for mais nova que a instalada, a página mostra o aviso, com o que mudou e como atualizar.

- **O que sai do computador:** só o pedido ``GET`` da última versão ao GitHub
  (``api.github.com/repos/lucasteles1231/editai/releases/latest``), sem nada de quem usa. O
  GitHub vê o IP, como em qualquer acesso.
- **Uma vez por dia:** a resposta fica guardada em ``versao.json``, na pasta de configuração.
  Sem internet, o Editai abre igual, sem aviso.
- **Para desligar:** "Não avisar mais", no próprio aviso, ou a variável
  ``EDITAI_SEM_AVISO_DE_VERSAO=1``.

**Atualizar:** ``editai --atualizar`` instala a última versão por cima, pelo ``uv``. No
Windows, ele mostra o comando do instalador: o ``editai.exe`` aberto não deixa trocar.

**A versão** é a do ``pyproject.toml`` (``editor.__version__`` repete, e um teste confere).
Cada versão publicada é uma tag ``vX.Y.Z``, com o pacote (``editai-X.Y.Z-py3-none-any.whl``)
e os instaladores anexados.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import httpx

from editor import __version__

REPOSITORIO = "lucasteles1231/editai"
API = f"https://api.github.com/repos/{REPOSITORIO}/releases/latest"
#: O site, com a documentação, as versões e os instaladores.
SITE = "https://lucasteles1231.github.io/editai"
#: ``falsa``: nunca pergunta ao GitHub (os testes).
VARIAVEL_FALSA = "EDITAI_VERSAO"
VARIAVEL_DESLIGA = "EDITAI_SEM_AVISO_DE_VERSAO"
#: De quanto em quanto tempo perguntar de novo; sem resposta, tenta de novo em 1 hora.
INTERVALO_S = 24 * 3600
INTERVALO_SEM_RESPOSTA_S = 3600
ESPERA_S = 5.0

_transporte = None


def numero(texto: str) -> tuple[int, int, int] | None:
    """``"v0.2.0"`` → ``(0, 2, 0)``; ``None`` para o que não é uma versão publicada (as
    prévias, como ``0.3.0-beta``, não avisam ninguém)."""
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", (texto or "").strip())
    return (int(m[1]), int(m[2]), int(m[3])) if m else None


def endereco_do_pacote(versao: str) -> str:
    return (f"https://github.com/{REPOSITORIO}/releases/download/v{versao}/"
            f"editai-{versao}-py3-none-any.whl")


def comando_do_instalador(sistema: str = sys.platform) -> str:
    """O comando de uma linha que instala (ou atualiza) pela versão mais nova do site."""
    if sistema == "win32":
        return f'powershell -ExecutionPolicy ByPass -c "irm {SITE}/instalar.ps1 | iex"'
    return f"curl -LsSf {SITE}/instalar.sh | sh"


def _falsa() -> bool:
    return os.environ.get(VARIAVEL_FALSA, "").strip().lower() == "falsa"


def _arquivo() -> Path:
    from editor import chaves

    return chaves.pasta_de_config() / "versao.json"


def _ler() -> dict:
    try:
        dados = json.loads(_arquivo().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return dados if isinstance(dados, dict) else {}


def _gravar(dados: dict) -> None:
    arquivo = _arquivo()
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")


def desligado() -> bool:
    return bool(os.environ.get(VARIAVEL_DESLIGA, "").strip()) or bool(_ler().get("silenciado"))


def silenciar() -> None:
    """"Não avisar mais": fica anotado no ``versao.json``."""
    _gravar({**_ler(), "silenciado": True})


def ultima(*, forcar: bool = False, agora: float | None = None) -> dict | None:
    """A última versão publicada (``{"versao", "endereco", "data"}``): a guardada, se tiver
    menos de um dia, ou a do GitHub. ``None`` sem resposta (sem internet, por exemplo)."""
    if _falsa():
        return None
    agora = time.time() if agora is None else agora
    guardado = _ler()
    espera = INTERVALO_S if guardado.get("ultima") else INTERVALO_SEM_RESPOSTA_S
    if not forcar and "quando" in guardado and agora - float(guardado["quando"] or 0) < espera:
        return guardado.get("ultima")
    resposta = None
    try:
        with httpx.Client(timeout=ESPERA_S, transport=_transporte) as cliente:
            r = cliente.get(API, headers={"Accept": "application/vnd.github+json",
                                          "User-Agent": f"Editai/{__version__}"})
        if r.status_code == 200:
            dados = r.json()
            if numero(str(dados.get("tag_name"))):
                resposta = {"versao": str(dados["tag_name"]).lstrip("v"),
                            "endereco": str(dados.get("html_url") or f"{SITE}/versoes"),
                            "data": str(dados.get("published_at") or "")[:10]}
    except (httpx.HTTPError, ValueError, KeyError):
        resposta = None
    _gravar({**guardado, "quando": agora, "ultima": resposta})
    return resposta


def _mais_nova(versao: str) -> bool:
    nova = numero(versao)
    return bool(nova) and nova > (numero(__version__) or (0, 0, 0))


def aviso(**kw) -> dict | None:
    """O aviso da página, quando há versão mais nova e ninguém desligou."""
    if desligado():
        return None
    u = ultima(**kw)
    if not u or not _mais_nova(u["versao"]):
        return None
    windows = sys.platform == "win32"
    return {"atual": __version__, "nova": u["versao"], "data": u.get("data", ""),
            "endereco": u["endereco"], "versoes": f"{SITE}/versoes",
            "comando": comando_do_instalador() if windows else "editai --atualizar",
            "fechar_antes": windows}


def atualizar(*, escrever=print, rodar=subprocess.run) -> int:
    """``editai --atualizar``: a última versão, instalada por cima pelo ``uv``."""
    u = ultima(forcar=True)
    if not u:
        escrever("Não consegui ver a última versão no GitHub. Tente de novo mais tarde, ou "
                 f"rode o instalador:\n  {comando_do_instalador()}")
        return 1
    if not _mais_nova(u["versao"]):
        escrever(f"Você já tem a versão mais nova ({__version__}).")
        return 0
    if sys.platform == "win32":
        escrever(f"A versão {u['versao']} saiu (você tem a {__version__}). Feche o Editai e "
                 f"cole no PowerShell:\n  {comando_do_instalador('win32')}")
        return 0
    from editor import motor_de_voz

    uv = motor_de_voz.achar_uv()
    if not uv:
        escrever(f"Não achei o uv. Rode o instalador:\n  {comando_do_instalador()}")
        return 1
    escrever(f"Atualizando de {__version__} para {u['versao']}…")
    r = rodar([uv, "tool", "install", "--force", "--python", "3.12",
               endereco_do_pacote(u["versao"])], check=False)
    if r.returncode != 0:
        escrever(f"O uv não conseguiu atualizar. Rode o instalador:\n  {comando_do_instalador()}")
        return 1
    # o atalho guarda a versão (no macOS, o Info.plist): o editai novo refaz o que já existe
    from editor import atalho

    if any(c.exists() for c in atalho.caminhos()):
        rodar(["editai", "--criar-atalho"], check=False)
    escrever(f"Pronto: o Editai {u['versao']} está instalado. O que mudou: {u['endereco']}")
    return 0


__all__ = ["API", "REPOSITORIO", "SITE", "VARIAVEL_DESLIGA", "VARIAVEL_FALSA", "atualizar",
           "aviso", "comando_do_instalador", "desligado", "endereco_do_pacote", "numero",
           "silenciar", "ultima"]
