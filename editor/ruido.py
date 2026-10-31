"""
O ruído da fala: o ventilador, o ar-condicionado, a rua, o teclado e o chiado do microfone saem
da voz, no computador, pelo DeepFilterNet3.

**Por que ele** (a prova de 31/10/2026, ``ferramentas/comparar_ruido.py``, num M5): a fala
limpa da voz Faber misturada a quatro ruídos, de 0 a 20 dB.

- **O DeepFilterNet3** subiu o SI-SDR de 6 a 18,6 dB em todos, e de 1,4 a 2,2 dB no burburinho
  (outras vozes), e limpa 1 min de áudio em 4,8 s. O dono ouviu e aprovou.
- **O portão espectral de antes** (``voz.tirar_ruido``) subia de 0,2 a 2,8 dB, e piorava o
  burburinho em até 19 dB.
- **O RNNoise** (o ``arnndn`` do FFmpeg) piorava o que tinha pouco ruído, e devolvia amostras
  ``nan`` de vez em quando.
- **O ``afftdn`` do FFmpeg** quase não mudava nada.

**O modelo:** o DeepFilterNet3 (de Hendrik Schröter, MIT/Apache-2.0), na versão "torchDF" de
fluxo, em ONNX. São dois arquivos de 13 MB do release ``model-dfn3-512-v1`` do
``deepfilter-stream`` (MIT), conferidos pelo SHA-256 e baixados só com o ok de quem usa
(:mod:`editor.componentes`). O jeito de rodar (512 amostras por vez, a 48 kHz, com o estado indo
e voltando) vem do ``deepfilter-stream``. O pacote não vem junto: ele arrasta o microfone ao
vivo e um reamostrador, e a voz do Editai já é 48 kHz.

**O atraso:** a saída sai 1.536 amostras (32 ms) atrás da entrada, pelos dois quadros que o
modelo olha à frente e pelo da janela. Aqui ela volta para o lugar, ou a voz sairia fora do
tempo da boca. O "leve" mistura a voz original no mesmo tempo (o pacote misturava a original
com só 512 amostras de atraso, e as duas, 21 ms fora, soavam "de tubo").

**O Auto** mede a folga entre a fala e o fundo (:func:`medir`):

- **mais de 30 dB:** não mexe;
- **de 15 a 30 dB:** o leve (tira no máximo 12 dB do ruído, e a voz fica mais natural);
- **menos de 15 dB:** o forte (tira tudo o que o modelo achar).

**E só com o fundo constante** (:func:`variacao_do_fundo`): o modelo guarda só a voz, e tiraria
junto a música e o som do jogo. Medido nas misturas da prova, o ventilador varia de 0,9 a 1,4 dB
nos trechos mais quietos; a música por baixo da fala, 3 dB; o teclado e as vozes ao fundo, de 16
a 20 dB. Acima de 2 dB, o Auto não mexe: o gameplay e o vlog com música ficam com o som deles.
Para tirar o teclado ou as vozes, quem edita escolhe o leve ou o forte.

A gravação com silêncio digital entre as falas (mais de 30% dos trechos abaixo de −90 dB) já
passou por um portão no aparelho que gravou: conta como limpa. É o caso das gravações do dono e
das vozes sintetizadas.

Para os testes, ``EDITOR_RUIDO=falso`` faz a limpeza devolver a voz como veio, sem modelo.
"""
from __future__ import annotations

import contextlib
import functools
import hashlib
import logging
import os
import threading
from collections.abc import Callable
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

TAXA = 48_000
#: O modelo, num release fixo, e os arquivos (o SHA-256 e os bytes, conferidos em 31/10/2026).
RELEASE = ("https://github.com/wuxuedaifu/deepfilter-stream/releases/download/"
           "model-dfn3-512-v1")
MODELO = "denoiser_model.onnx"
ESTADOS = "initial_states.npz"
ARQUIVOS = {MODELO: ("b758c49d6708a5b7979e3de185705a8a4915076c862fb17b1b304d9a72b75cdc",
                     12_911_035),
            ESTADOS: ("1165503707b8859a6b650b6bb0dc5b6c55d30c2779d87502f97a77102b5d3872",
                      187_714)}
BYTES = sum(b for _, b in ARQUIVOS.values())
#: O quadro do modelo e o atraso da saída, em amostras.
QUADRO = 512
ATRASO = 1536

#: As escolhas de quem edita, e a força que o Auto escolhe pela folga medida.
OPCOES = ("auto", "leve", "forte", "nao")
LIMIAR_DB = 30.0
FORTE_ABAIXO_DE_DB = 15.0
#: O fundo constante (o ventilador, o chiado): o Auto só limpa abaixo desta variação.
FUNDO_CONSTANTE_DB = 2.0
#: O leve tira no máximo isto do ruído.
LEVE_DB = 12.0
#: O silêncio digital (o portão do aparelho), e quanto dele faz a gravação contar como limpa.
SILENCIO_DIGITAL_DB = -90.0
LIMPA_COM_SILENCIO = 0.3
#: A folga de uma gravação limpa (o que :func:`medir` devolve para ela).
FOLGA_DA_LIMPA = 99.0

VARIAVEL_FALSA = "EDITOR_RUIDO"
ESPERA_DO_DOWNLOAD_S = 60.0

#: O andamento: a fração e um texto curto.
Andamento = Callable[[float, str], None]

_transporte = None


class ErroDoRuido(Exception):
    pass


def falso() -> bool:
    return os.environ.get(VARIAVEL_FALSA, "").strip().lower() == "falso"


def pasta() -> Path:
    from platformdirs import user_data_dir

    return Path(user_data_dir("editor-de-video", appauthor=False)) / "ruido" / "dfn3-512-v1"


def instalado() -> bool:
    """Se os dois arquivos estão no computador, com o tamanho certo (o SHA-256 foi conferido
    ao baixar)."""
    if falso():
        return True
    return all((pasta() / nome).is_file() and (pasta() / nome).stat().st_size == tamanho
               for nome, (_sha, tamanho) in ARQUIVOS.items())


def _sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def baixar(andamento: Andamento | None = None,
           cancelar: Callable[[], bool] = lambda: False) -> None:
    """Baixa os dois arquivos do release fixo, com o andamento em bytes, e confere o SHA-256.
    Só depois do ok de quem usa: quem chama é :func:`editor.componentes.baixar`."""
    import httpx

    from editor import componentes

    andamento = andamento or (lambda fracao, texto: None)
    destino = pasta()
    destino.mkdir(parents=True, exist_ok=True)
    feito = 0
    andamento(0.0, f"0 de {componentes.legivel(BYTES)}")
    with httpx.Client(timeout=ESPERA_DO_DOWNLOAD_S, transport=_transporte,
                      follow_redirects=True) as cliente:
        for nome, (sha, tamanho) in ARQUIVOS.items():
            final = destino / nome
            if final.is_file() and final.stat().st_size == tamanho and _sha256(final) == sha:
                feito += tamanho
                continue
            parcial = final.with_suffix(final.suffix + ".parcial")
            with cliente.stream("GET", f"{RELEASE}/{nome}") as r, parcial.open("wb") as f:
                r.raise_for_status()
                for pedaco in r.iter_bytes(1024 * 256):
                    if cancelar():
                        raise InterruptedError("download cancelado")
                    f.write(pedaco)
                    feito += len(pedaco)
                    andamento(min(1.0, feito / BYTES),
                              f"{componentes.legivel(feito)} de {componentes.legivel(BYTES)}")
            if _sha256(parcial) != sha:
                parcial.unlink(missing_ok=True)
                raise ErroDoRuido(f"O modelo do ruído baixado não confere ({nome}: o SHA-256 é "
                                  "outro). Tente de novo.")
            parcial.replace(final)
    andamento(1.0, componentes.legivel(BYTES))


# ── a medida ──────────────────────────────────────────────────────────────
def _niveis(x: np.ndarray, taxa: int) -> np.ndarray | None:
    """O nível de cada trecho de 20 ms, em dB, sem o silêncio digital (``None`` se a gravação
    tem silêncio digital demais, ou é curta demais)."""
    n = int(0.02 * taxa)
    if len(x) < n * 10:
        return None
    janelas = np.asarray(x[: len(x) // n * n], dtype=np.float64).reshape(-1, n)
    db = 20 * np.log10(np.sqrt((janelas ** 2).mean(axis=1)) + 1e-12)
    som = db[db > SILENCIO_DIGITAL_DB]
    if len(som) < 10 or 1 - len(som) / len(db) > LIMPA_COM_SILENCIO:
        return None
    return som


def variacao_do_fundo(x: np.ndarray, taxa: int = TAXA) -> float:
    """O quanto o fundo varia: dos 5% aos 20% de trechos mais quietos, em dB. O ventilador
    fica perto de 1 dB; a música, o teclado e as vozes passam de 2."""
    som = _niveis(x, taxa)
    return 0.0 if som is None else float(np.percentile(som, 20) - np.percentile(som, 5))


def medir(x: np.ndarray, taxa: int = TAXA) -> float:
    """A folga entre a fala (os 10% de trechos de 20 ms mais fortes) e o fundo (os 10% mais
    quietos), em dB, sem contar o silêncio digital. Com muito silêncio digital, a gravação já
    passou por um portão: :data:`FOLGA_DA_LIMPA`."""
    som = _niveis(x, taxa)
    if som is None:
        return FOLGA_DA_LIMPA
    return float(np.percentile(som, 90) - np.percentile(som, 10))


@functools.lru_cache(maxsize=64)
def _medidas_do_arquivo(caminho: str, tamanho: int, mudado: float) -> tuple[float, float]:
    # A 48 kHz, a banda inteira: a 16 kHz, o reamostrador corta o que passa de 8 kHz, e o
    # chiado, que mora ali, saía uns 5 dB mais baixo do que é.
    from editor import video as video_mod

    x = video_mod.ler_audio_mono(Path(caminho), TAXA)
    return medir(x, TAXA), variacao_do_fundo(x, TAXA)


def medidas_do_arquivo(caminho: Path) -> tuple[float, float]:
    """A folga e a variação do fundo de um arquivo (vídeo ou áudio), guardadas enquanto ele
    não mudar."""
    caminho = Path(caminho)
    try:
        info = caminho.stat()
    except OSError:
        return FOLGA_DA_LIMPA, 0.0
    try:
        return _medidas_do_arquivo(str(caminho), info.st_size, info.st_mtime)
    except Exception as erro:             # um arquivo sem som não tem ruído para tirar
        logger.info("não deu para medir o ruído de %s: %s", caminho.name, erro)
        return FOLGA_DA_LIMPA, 0.0


def folga_do_arquivo(caminho: Path) -> float:
    return medidas_do_arquivo(caminho)[0]


def forca(opcao: str, folga_db: float, variacao_db: float = 0.0) -> str:
    """O que fazer: ``"nada"``, ``"leve"`` ou ``"forte"``. O Auto só mexe com o fundo
    constante."""
    if opcao in ("leve", "forte"):
        return opcao
    if opcao != "auto" or folga_db >= LIMIAR_DB or variacao_db > FUNDO_CONSTANTE_DB:
        return "nada"
    return "forte" if folga_db < FORTE_ABAIXO_DE_DB else "leve"


def forca_dos_arquivos(opcao: str, arquivos) -> tuple[str, float]:
    """A força para uma fala de vários arquivos (vale o mais ruidoso) e a folga dele."""
    if opcao == "nao" or not arquivos:
        return "nada", FOLGA_DA_LIMPA
    if opcao != "auto":
        return forca(opcao, FOLGA_DA_LIMPA), FOLGA_DA_LIMPA
    medidas = [medidas_do_arquivo(a) for a in arquivos]
    folga, variacao = min(medidas)
    return forca(opcao, folga, variacao), folga


# ── a limpeza ─────────────────────────────────────────────────────────────
_sessao = None
_estados: dict[str, np.ndarray] = {}
_trava = threading.Lock()


def _carregar():
    global _sessao, _estados
    with _trava:
        if _sessao is None:
            import onnxruntime

            opcoes = onnxruntime.SessionOptions()
            opcoes.log_severity_level = 3
            _sessao = onnxruntime.InferenceSession(str(pasta() / MODELO), sess_options=opcoes,
                                                   providers=["CPUExecutionProvider"])
            nomes = [i.name for i in _sessao.get_inputs()][1:]
            with np.load(pasta() / ESTADOS) as z:
                _estados = {nome: z[nome].astype(np.float32) for nome in nomes}
        return _sessao


def soltar() -> None:
    """Devolve a memória do modelo (ele volta em menos de 1 s)."""
    global _sessao, _estados
    with _trava:
        _sessao, _estados = None, {}


def limpar(x: np.ndarray, forca_: str = "forte",
           andamento: Callable[[float], None] | None = None,
           parar: Callable[[], bool] = lambda: False) -> np.ndarray:
    """A voz mono a 48 kHz sem o ruído, no mesmo comprimento e no mesmo tempo."""
    x = np.ascontiguousarray(x, dtype=np.float32).reshape(-1)
    if forca_ == "nada" or not len(x):
        return x
    if falso():
        if andamento:
            andamento(1.0)
        return x.copy()
    if not instalado():
        raise ErroDoRuido("O modelo do ruído não está no computador.")
    sessao = _carregar()
    entradas = [i.name for i in sessao.get_inputs()]
    saidas = [o.name for o in sessao.get_outputs()]
    estados = {k: v.copy() for k, v in _estados.items()}
    # o fim ganha o atraso em zeros, para a última fala também sair
    total = len(x) + ATRASO
    quadros = -(-total // QUADRO)
    entrada = np.zeros(quadros * QUADRO, np.float32)
    entrada[:len(x)] = x
    saida = np.empty_like(entrada)
    for k in range(quadros):
        if k % 200 == 0:
            if parar():
                raise InterruptedError("cancelado")
            if andamento:
                andamento(k / quadros)
        feeds = {entradas[0]: entrada[k * QUADRO:(k + 1) * QUADRO], **estados}
        resultado = sessao.run(saidas, feeds)
        saida[k * QUADRO:(k + 1) * QUADRO] = np.asarray(resultado[0], np.float32).reshape(-1)
        estados = dict(zip(entradas[1:], resultado[1:], strict=True))
    limpa = saida[ATRASO:ATRASO + len(x)]
    if forca_ == "leve":
        resto = float(10 ** (-LEVE_DB / 20))
        limpa = resto * x + (1 - resto) * limpa
    if andamento:
        andamento(1.0)
    return np.nan_to_num(limpa, nan=0.0).astype(np.float32)


def desinstalar() -> int:
    """Tira o modelo do computador; devolve os bytes que saíram."""
    import shutil

    soltar()
    raiz = pasta()
    if not raiz.exists():
        return 0
    saiu = sum(p.stat().st_size for p in raiz.rglob("*") if p.is_file())
    with contextlib.suppress(OSError):
        shutil.rmtree(raiz)
    return saiu


__all__ = ["ATRASO", "BYTES", "FUNDO_CONSTANTE_DB", "LIMIAR_DB", "OPCOES", "VARIAVEL_FALSA",
           "ErroDoRuido", "baixar", "desinstalar", "falso", "folga_do_arquivo", "forca",
           "forca_dos_arquivos", "instalado", "limpar", "medidas_do_arquivo", "medir", "pasta",
           "soltar", "variacao_do_fundo"]
