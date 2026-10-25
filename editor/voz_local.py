"""
A voz local: o Piper com a voz ``pt_BR-faber-medium``, num ambiente só dele.

**Por que à parte.** O pacote ``piper-tts`` é GPL-3 (ele embute o espeak-ng, que transforma o
texto em fonemas), e o Editai é MIT. Importado aqui, ele levaria a licença dele junto; rodando
num ambiente próprio, como outro programa que o editor chama, cada um fica com a sua. É o
mesmo jeito do motor da voz sintetizada (:mod:`editor.motor_de_voz`). A voz faber é MIT,
treinada em dados CC0.

**A instalação** (o botão da página, ou ``editai --instalar-voz-local``):

1. o ``uv`` cria o ambiente com o Python 3.12 e instala o ``piper-tts`` na versão testada (sem
   o ``uv``, valem o ``venv`` e o ``pip``);
2. a voz (63 MB) vem do Hugging Face num commit fixo, conferida pelo SHA-256;
3. o motor lê uma frase de teste.

Uns 210 MB no total, medidos num Mac em 25/10/2026: o ONNX Runtime (76 MB), o
Piper com o espeak (45 MB), a voz (60 MB) e o resto do ambiente.

**A conversa** é a do motor de voz: um pedido em JSON, um processo por narração, e uma linha
JSON a cada frase pronta. O Piper carrega em menos de um segundo e lê umas 10 vezes mais
rápido que a fala (27× num Mac M5; 11,7× numa VPS de 1 núcleo, sem placa).

**A leitura** (:func:`para_ler`): o espeak lê os algarismos, mas não o "R$" nem o "%"; essas
trocas são feitas aqui, antes de mandar o texto.

Para os testes vale a voz falsa do motor de voz (``EDITOR_VOZ=falsa``): cada frase vira um tom
da duração que a fala teria.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from collections.abc import Callable
from importlib.resources import files
from pathlib import Path

from editor import motor_de_voz

logger = logging.getLogger(__name__)

PACOTE = "piper-tts==1.8.0"
PYTHON = "3.12"
REPO = "rhasspy/piper-voices"
#: O commit da voz no Hugging Face (conferido em 25/10/2026).
REVISAO = "5041a7a49ae5b3a0f30e6837769eb03fdbb231bd"
MODELO = "pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx"
#: Os arquivos da voz e o SHA-256 de cada um (o JSON é pequeno e vem no mesmo commit).
ARQUIVOS = {MODELO: "858555e3a064209c57088fe6bd70c4c3dc54d03eaa00c45d5ecaf43a33f95aa7",
            MODELO + ".json": None}
ESPACO = "uns 210 MB"
TEMPO = "de 1 a 3 minutos, conforme a internet"

ETAPAS = {"ambiente": ("Criando o ambiente", 0.0, 0.1),
          "pacotes": ("Instalando o Piper", 0.1, 0.55),
          "voz": ("Baixando a voz (63 MB)", 0.55, 0.95),
          "teste": ("Testando a voz", 0.95, 1.0)}


class ErroDaVozLocal(RuntimeError):
    """A instalação ou a síntese falharam (a mensagem diz o que fazer)."""


def falso() -> bool:
    return motor_de_voz.falso()


def pasta() -> Path:
    from editor.ia import pasta_de_dados

    return pasta_de_dados() / "voz-local"


def caminho_do_modelo() -> Path:
    return pasta() / "voz" / Path(MODELO).name


def python_da_voz() -> Path:
    venv = pasta() / ".venv"
    return venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def script() -> Path:
    return Path(str(files("editor").joinpath("recursos", "voz_local.py")))


def _marca() -> Path:
    return pasta() / "instalado.json"


def instalado() -> bool:
    return falso() or (_marca().is_file() and python_da_voz().is_file()
                       and caminho_do_modelo().is_file())


def identidade() -> str:
    """O que muda o som: o pacote e a voz. Entra na chave do cache das frases."""
    return f"piper|{PACOTE}|{REPO}@{REVISAO}|{MODELO}"


# ── a leitura ────────────────────────────────────────────────────────────

_NUMERO = r"\d[\d.,]*(?:\s+(?:milhões|milhão|bilhões|bilhão|trilhões|trilhão|mil)\b)?"


def _moeda(nome: str):
    # "170 milhões de reais", mas "3,5 mil reais" e "20 reais"
    return lambda m: f"{m.group(1)} {'de ' if re.search(r'(ão|ões)$', m.group(1)) else ''}{nome}"


_TROCAS = [
    (re.compile(rf"R\$\s*({_NUMERO})", re.I), _moeda("reais")),
    (re.compile(rf"US\$\s*({_NUMERO})", re.I), _moeda("dólares")),
    (re.compile(rf"€\s*({_NUMERO})"), _moeda("euros")),
    (re.compile(r"(\d)\s*%"), lambda m: f"{m.group(1)} por cento"),
    (re.compile(r"(\d)\s*km/h\b", re.I), lambda m: f"{m.group(1)} quilômetros por hora"),
    (re.compile(r"(\d)\s*°C\b"), lambda m: f"{m.group(1)} graus"),
]


def para_ler(texto: str) -> str:
    """O texto como a voz deve ler: o dinheiro, a porcentagem e as unidades por extenso (a
    legenda continua com a grafia do roteiro)."""
    for padrao, troca in _TROCAS:
        texto = padrao.sub(troca, texto)
    return re.sub(r"\s+", " ", texto).strip()


# ── a instalação ─────────────────────────────────────────────────────────


class _Instalacao:
    def __init__(self) -> None:
        self.rodando = False
        self.etapa = ""
        self.fracao = 0.0
        self.erro = ""
        self.linhas: list[str] = []
        self.parar = threading.Event()


_instalacao = _Instalacao()
_trava = threading.Lock()


def estado() -> dict:
    from editor import desinstalar

    i = _instalacao
    ocupa = desinstalar.tamanho(pasta()) if instalado() and not falso() else 0
    return {"instalado": instalado(), "instalando": i.rodando,
            "etapa": ETAPAS.get(i.etapa, (i.etapa,))[0] if i.etapa else "",
            "fracao": round(i.fracao, 3), "erro": i.erro, "espaco": ESPACO, "tempo": TEMPO,
            "ocupa": desinstalar.legivel(ocupa) if ocupa else ""}


def _ambiente() -> dict:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    for nome in ("VIRTUAL_ENV", "PYTHONPATH", "PYTHONHOME"):
        env.pop(nome, None)
    return env


def comandos() -> list[tuple[str, list[str]]]:
    venv, py = pasta() / ".venv", str(python_da_voz())
    uv = motor_de_voz.achar_uv()
    if uv:
        return [("ambiente", [uv, "venv", "--python", PYTHON, "--allow-existing", str(venv)]),
                ("pacotes", [uv, "pip", "install", "--python", py, PACOTE])]
    return [("ambiente", [sys.executable, "-m", "venv", str(venv)]),
            ("pacotes", [py, "-m", "pip", "install", PACOTE])]


def _rodar(comando: list[str], parar: threading.Event) -> tuple[int, list[str]]:
    proc = subprocess.Popen(comando, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            env=_ambiente(), cwd=str(pasta()))
    assert proc.stdout is not None
    linhas: list[str] = []
    for bruta in iter(proc.stdout.readline, b""):
        linha = bruta.decode("utf-8", "replace").strip()
        if linha:
            linhas.append(linha[:300])
        if parar.is_set():
            proc.terminate()
            break
    return proc.wait(), linhas[-3:]


def _sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def _baixar_a_voz() -> None:
    from huggingface_hub import hf_hub_download

    destino = caminho_do_modelo().parent
    destino.mkdir(parents=True, exist_ok=True)
    for nome, sha in ARQUIVOS.items():
        baixado = Path(hf_hub_download(REPO, nome, revision=REVISAO))
        if sha and _sha256(baixado) != sha:
            raise ErroDaVozLocal("A voz baixada não confere com a esperada (o SHA-256 é outro). "
                                 "Tente instalar de novo.")
        shutil.copyfile(baixado, destino / Path(nome).name)


def _executar() -> dict:
    i = _instalacao
    try:
        if falso():
            i.etapa, i.fracao = "teste", 1.0
            return {}
        pasta().mkdir(parents=True, exist_ok=True)
        for etapa, comando in comandos():
            nome, a, b = ETAPAS[etapa]
            i.etapa, i.fracao = etapa, a
            codigo, ultimas = _rodar(comando, i.parar)
            if i.parar.is_set():
                raise ErroDaVozLocal("A instalação foi cancelada.")
            if codigo != 0:
                raise ErroDaVozLocal(f"{nome} falhou (código {codigo}): {' | '.join(ultimas)}")
            i.fracao = b
        i.etapa, i.fracao = "voz", ETAPAS["voz"][1]
        _baixar_a_voz()
        i.etapa, i.fracao = "teste", ETAPAS["teste"][1]
        codigo, ultimas = _rodar([str(python_da_voz()), "-I", str(script()), "--conferir",
                                  str(caminho_do_modelo())], i.parar)
        if codigo != 0:
            raise ErroDaVozLocal(f"A voz não leu a frase de teste: {' | '.join(ultimas)}")
        registro = {"pacote": PACOTE, "repo": REPO, "revisao": REVISAO, "modelo": MODELO,
                    "quando": time.strftime("%Y-%m-%d")}
        _marca().write_text(json.dumps(registro, ensure_ascii=False, indent=1),
                            encoding="utf-8")
        i.fracao = 1.0
        return registro
    except ErroDaVozLocal as erro:
        i.erro = str(erro)
        raise
    except Exception as erro:
        i.erro = f"A instalação falhou: {type(erro).__name__}: {erro}"
        raise ErroDaVozLocal(i.erro) from erro
    finally:
        i.rodando = False


def _comecar() -> None:
    i = _instalacao
    with _trava:
        if i.rodando:
            raise ErroDaVozLocal("A instalação já está rodando.")
        i.rodando, i.erro, i.etapa, i.fracao = True, "", "", 0.0
        i.linhas = []
        i.parar.clear()


def instalar() -> dict:
    """Instala a voz local (bloqueia até o fim)."""
    _comecar()
    return _executar()


def instalar_em_segundo_plano() -> dict:
    _comecar()

    def rodar() -> None:
        try:
            _executar()
        except ErroDaVozLocal:
            logger.exception("a voz local não instalou")

    threading.Thread(target=rodar, daemon=True, name="instalar-a-voz-local").start()
    return estado()


def cancelar_instalacao() -> None:
    _instalacao.parar.set()


def desinstalar() -> None:
    if _instalacao.rodando:
        raise ErroDaVozLocal("Espere a instalação terminar (ou cancele) para desinstalar.")
    shutil.rmtree(pasta(), ignore_errors=True)


# ── a síntese ────────────────────────────────────────────────────────────


def sintetizar(frases: list[tuple[str, Path]], *,
               progresso: Callable[[int, int], None] | None = None,
               parar: Callable[[], bool] | None = None) -> str:
    """Gera cada frase no WAV indicado. Devolve "local" (ou "falso", nos testes)."""
    if falso():
        for k, (texto, saida) in enumerate(frases):
            motor_de_voz._tom(texto, saida)
            if progresso:
                progresso(k + 1, len(frases))
        return "falso"
    if not instalado():
        raise ErroDaVozLocal("A voz local não está instalada: instale pelo botão da página ou "
                             "com editai --instalar-voz-local.")
    pedido = {"modelo": str(caminho_do_modelo()),
              "frases": [{"texto": t, "saida": str(s)} for t, s in frases]}
    with tempfile.TemporaryDirectory(prefix="pedido-") as tmp:
        arquivo = Path(tmp) / f"{uuid.uuid4().hex[:8]}.json"
        arquivo.write_text(json.dumps(pedido, ensure_ascii=False), encoding="utf-8")
        erros = Path(tmp) / "erros.txt"
        with erros.open("wb") as saida_de_erro:
            proc = subprocess.Popen([str(python_da_voz()), "-I", str(script()), str(arquivo)],
                                    stdout=subprocess.PIPE, stderr=saida_de_erro,
                                    env=_ambiente())
            assert proc.stdout is not None
            for bruta in iter(proc.stdout.readline, b""):
                with contextlib.suppress(ValueError):
                    msg = json.loads(bruta.decode("utf-8", "replace"))
                    if "feitas" in msg and progresso:
                        progresso(int(msg["feitas"]), len(frases))
                if parar and parar():
                    proc.terminate()
                    proc.wait()
                    raise ErroDaVozLocal("A narração foi cancelada.")
            codigo = proc.wait()
        if codigo != 0:
            final = erros.read_text(encoding="utf-8", errors="replace").strip().splitlines()
            raise ErroDaVozLocal(f"A voz local falhou (código {codigo}): "
                                 f"{' | '.join(final[-3:]) or 'sem mensagem'}")
    faltando = [str(s) for _t, s in frases if not Path(s).is_file()]
    if faltando:
        raise ErroDaVozLocal(f"A voz local não gerou {len(faltando)} frase(s).")
    return "local"


__all__ = ["ARQUIVOS", "ESPACO", "MODELO", "PACOTE", "REVISAO", "TEMPO", "ErroDaVozLocal",
           "cancelar_instalacao", "comandos", "desinstalar", "estado", "falso", "identidade",
           "instalado", "instalar", "instalar_em_segundo_plano", "para_ler", "pasta",
           "sintetizar"]
