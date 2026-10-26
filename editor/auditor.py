"""
O auditor das imagens: confere, no próprio computador, se uma foto mostra o que a descrição
diz. Ele escolhe as fotos do vídeo só pelo tema (:mod:`editor.fotos`): de cada busca, ficam as
que mais combinam com o trecho, e não as primeiras que o banco de fotos devolveu.

Usa o SigLIP 2 (``google/siglip2-base-patch16-224``, do Google, Apache 2.0), na exportação ONNX
da onnx-community, quantizada em int8: a parte da imagem (95 MB), a do texto (283 MB) e o
vocabulário (34 MB), uns 410 MB ao todo. Ele lê a descrição em português e roda pelo
``onnxruntime``, o mesmo do recorte. Os arquivos vêm do Hugging Face no primeiro uso, num
commit fixo e conferidos pelo SHA-256, e daí em diante são lidos do cache, sem rede.

**A nota** é o cosseno entre a imagem e o texto no espaço do modelo: perto de 0 quando não têm
nada a ver, e de 0,10 a 0,18 quando a foto mostra o que o texto diz. O SigLIP também dá uma
probabilidade, mas ela foi calibrada em legendas curtas, e as nossas descrições ficavam todas
perto de zero; o cosseno separa melhor.

**O que foi medido** (25/10/2026, num Mac M5):

- **nas 100 cenas de um trailer,** cada uma com a descrição que a IA escreveu olhando o quadro:
  a própria cena saiu em 1º lugar em 67% das vezes, e entre as 5 primeiras em 97%. O int8
  acerta o mesmo que o modelo inteiro (fp32) com um quarto do tamanho. O ``*_quantized`` da
  exportação é o uint8 da imagem, que errava o dobro: por isso os arquivos são os ``*_int8``;
- **nas 46 fotos de um vídeo sobre o GPS,** as que não tinham nada a ver (uma aranha no lugar
  de um satélite, o mar no lugar de quatro satélites, uma mulher tatuada no lugar de três
  esferas) ficaram abaixo de :data:`PISO`, e as boas, acima;
- **o tempo:** 32 ms por imagem e 10 ms por texto.

Para os testes há o auditor falso (``EDITOR_AUDITOR=falso``): a mesma nota para todas as
imagens, que ficam na ordem em que vieram, sem baixar o modelo.
"""
from __future__ import annotations

import contextlib
import hashlib
import itertools
import logging
import os
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

#: O modelo, num commit fixo: o mesmo arquivo para todo mundo, e ele só muda com uma versão
#: nova do editor.
REPOSITORIO = "onnx-community/siglip2-base-patch16-224-ONNX"
REVISAO = "ba1f3b0843f24bc5417d38e19c37b287d719b2f4"
IMAGEM = "onnx/vision_model_int8.onnx"
TEXTO = "onnx/text_model_int8.onnx"
VOCABULARIO = "tokenizer.json"
#: Os arquivos e o SHA-256 de cada um (conferidos em 25/10/2026).
ARQUIVOS = {IMAGEM: "0dd31785a2713f1113ef2272472165c69d580473dae38d7b47568ac587795e70",
            TEXTO: "3a0603d3a00c05a80a6ded4743c16aaac7b1e62cdcc7e362e7ce418659b96400",
            VOCABULARIO: "cb9140fae3ac5122c972d37adf83e1248471a38147ad76f8215c8872c6fd8322"}
TAMANHO = "uns 410 MB"

#: Abaixo desta nota, a foto não mostra o que o texto diz (calibrado nas fotos do GPS).
PISO = 0.06
#: Duas fotos mais parecidas que isto (imagem contra imagem) são a mesma cena: o banco de
#: fotos devolve várias da mesma sessão, e o vídeo mostraria a mesma foto duas vezes. Nas
#: prévias, as da mesma sessão deram de 0,90 a 0,98, e 90% dos outros pares, menos de 0,87.
#: Duas fotos diferentes da mesma coisa (duas ampulhetas) dão de 0,89 a 0,93 e também saem:
#: no vídeo do GPS, nenhum trecho ficou sem as suas 2 fotos por isso.
PARECIDA = 0.90
#: O lado da imagem e o tamanho do texto, em tokens, que o modelo recebe.
LADO = 224
TOKENS = 64
#: Quantas imagens o modelo recebe de cada vez: a velocidade é a mesma (32 ms por imagem num
#: Mac M5), e o pico de memória cai de 615 MB (com 12 de uma vez) para 295 MB.
LOTE = 2
#: Os textos rodam num processo à parte (:func:`lembrar`); os testes trocam por ``False``.
PROCESSO_A_PARTE = True

#: A variável que liga o auditor falso (só testes).
VARIAVEL_FALSA = "EDITOR_AUDITOR"

# O mesmo aviso que a transcrição e o recorte desligam: o Hugging Face pede um token no
# primeiro download, e não é preciso conta nenhuma.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("HF_HUB_VERBOSITY", "error")


class ErroDoAuditor(RuntimeError):
    """O modelo não veio ou não confere (a mensagem diz o que fazer)."""


@dataclass
class Notas:
    """A nota de cada imagem contra o texto e o vetor de cada uma (para achar as repetidas)."""

    notas: list[float]
    vetores: np.ndarray


def falso() -> bool:
    return os.environ.get(VARIAVEL_FALSA, "").strip().lower() == "falso"


def baixado() -> bool:
    """Se os três arquivos já estão no cache: para avisar do download antes de começar."""
    if falso():
        return True
    try:
        from huggingface_hub import hf_hub_download

        for nome in ARQUIVOS:
            hf_hub_download(REPOSITORIO, nome, revision=REVISAO, local_files_only=True)
        return True
    except Exception:
        return False


def _sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def _arquivo(nome: str) -> Path:
    """O arquivo no cache; baixado agora, ele é conferido pelo SHA-256 (o do cache já foi)."""
    from huggingface_hub import hf_hub_download

    try:
        return Path(hf_hub_download(REPOSITORIO, nome, revision=REVISAO, local_files_only=True))
    except Exception:
        pass
    caminho = Path(hf_hub_download(REPOSITORIO, nome, revision=REVISAO))
    if _sha256(caminho) != ARQUIVOS[nome]:
        # o arquivo errado sai do cache, para a próxima tentativa baixar de novo
        for lixo in (caminho.resolve(), caminho):
            with contextlib.suppress(OSError):
                lixo.unlink()
        raise ErroDoAuditor(f"O auditor baixado não confere ({nome}: o SHA-256 é outro). "
                            "Tente de novo.")
    return caminho


_sessoes: dict[str, object] = {}
_vocabulario = None
#: Os vetores dos textos já calculados (a parte do texto fecha depois deles).
_textos: dict[str, np.ndarray] = {}
_trava = threading.Lock()


def _sessao(nome: str):
    """A sessão do onnxruntime de uma das partes do modelo, aberta na primeira vez."""
    with _trava:
        if nome not in _sessoes:
            import onnxruntime

            opcoes = onnxruntime.SessionOptions()
            opcoes.log_severity_level = 3
            _sessoes[nome] = onnxruntime.InferenceSession(
                str(_arquivo(nome)), sess_options=opcoes, providers=["CPUExecutionProvider"])
        return _sessoes[nome]


def _codificar(textos: Sequence[str]) -> np.ndarray:
    global _vocabulario
    with _trava:
        if _vocabulario is None:
            from tokenizers import Tokenizer

            vocabulario = Tokenizer.from_file(str(_arquivo(VOCABULARIO)))
            vocabulario.enable_truncation(TOKENS)
            vocabulario.enable_padding(length=TOKENS, pad_id=0, pad_token="<pad>")
            _vocabulario = vocabulario
    # o SigLIP 2 foi treinado com o texto em minúsculas
    return np.array([_vocabulario.encode(" ".join(t.split()).lower()).ids for t in textos],
                    dtype=np.int64)


def _vetores_dos_textos(textos: list[str]) -> np.ndarray:
    """Os vetores dos ``textos``, com o vocabulário e a parte do texto abertos aqui."""
    sessao = _sessao(TEXTO)
    vetores = [sessao.run(["pooler_output"], {"input_ids": _codificar(textos[i:i + 16])})[0]
               for i in range(0, len(textos), 16)]
    return _normalizar(np.concatenate(vetores))


def _no_processo_a_parte(textos: list[str]) -> np.ndarray:
    import multiprocessing
    from concurrent.futures import ProcessPoolExecutor

    with ProcessPoolExecutor(1, mp_context=multiprocessing.get_context("spawn")) as processo:
        return processo.submit(_vetores_dos_textos, textos).result()


def lembrar(textos: Sequence[str]) -> None:
    """Calcula de uma vez os vetores dos ``textos``, num processo à parte, que devolve a
    memória ao sair. O vocabulário (386 MB, com 256 mil pedaços de palavra) e a parte do texto
    (684 MB) não voltam para o sistema depois de fechados: o editor ficaria com 1,1 GB pelo resto
    do dia (medido num Mac em 26/10/2026). Os textos de um vídeo inteiro saem em 2 s."""
    global _vocabulario
    faltam = [t for t in dict.fromkeys(textos) if t not in _textos]
    if not faltam or falso():
        return
    vetores = None
    if PROCESSO_A_PARTE:
        try:
            vetores = _no_processo_a_parte(faltam)
        except Exception as erro:
            logger.info("os textos do auditor vão rodar aqui mesmo: %s", erro)
    if vetores is None:
        try:
            vetores = _vetores_dos_textos(faltam)
        finally:
            with _trava:
                _sessoes.pop(TEXTO, None)
                _vocabulario = None
    _textos.update(zip(faltam, vetores, strict=True))


def preparar(textos: Sequence[str] = ()) -> bool:
    """Baixa o modelo na primeira vez, calcula os ``textos`` e abre a parte da imagem.
    ``False`` se não deu: sem internet na primeira vez, por exemplo."""
    if falso():
        return True
    try:
        for nome in ARQUIVOS:
            _arquivo(nome)
        lembrar(textos)
        _sessao(IMAGEM)
        return True
    except Exception as erro:
        logger.warning("o auditor das imagens não carregou: %s", erro)
        return False


def soltar() -> None:
    """Devolve a memória do modelo: o servidor fica aberto o dia todo, e o auditor só trabalha
    enquanto as fotos são escolhidas. Ele volta em menos de 1 s, do cache."""
    global _vocabulario
    with _trava:
        _sessoes.clear()
        _textos.clear()
        _vocabulario = None


def _normalizar(vetores: np.ndarray) -> np.ndarray:
    vetores = np.asarray(vetores, dtype=np.float32)
    return vetores / np.maximum(np.linalg.norm(vetores, axis=1, keepdims=True), 1e-8)


def _pixels(imagens: Sequence[Image.Image]) -> np.ndarray:
    """As imagens no formato do modelo: N × 3 × 224 × 224, de -1 a 1 (o redimensionamento
    sem recorte do processador do SigLIP)."""
    x = np.stack([np.asarray(i.convert("RGB").resize((LADO, LADO), Image.BILINEAR),
                             dtype=np.float32) for i in imagens])
    return np.ascontiguousarray(((x / 255.0 - 0.5) / 0.5).transpose(0, 3, 1, 2))


_sorteio = itertools.count()


def avaliar(imagens: Sequence[Image.Image], texto: str) -> Notas:
    """A nota de cada imagem contra o ``texto``."""
    if not imagens:
        return Notas([], np.zeros((0, 0), np.float32))
    if falso():
        # a mesma nota para todas, e vetores sorteados, que nunca se parecem: a ordem fica a
        # de chegada, e nenhuma foto conta como repetida
        sorteados = np.random.default_rng(next(_sorteio)).standard_normal((len(imagens), 64))
        return Notas([PISO + 0.05] * len(imagens), _normalizar(sorteados))
    lembrar([texto])
    alvo = _textos[texto]
    sessao = _sessao(IMAGEM)
    vetores = _normalizar(np.concatenate([
        sessao.run(["pooler_output"], {"pixel_values": _pixels(imagens[i:i + LOTE])})[0]
        for i in range(0, len(imagens), LOTE)]))
    return Notas([round(float(v), 4) for v in vetores @ alvo], vetores)


def juntar(a: Notas, b: Notas) -> Notas:
    """As notas de duas levas de imagens, uma depois da outra."""
    if not a.notas:
        return b
    if not b.notas:
        return a
    return Notas(a.notas + b.notas, np.vstack([a.vetores, b.vetores]))


def escolher(n: Notas, quantas: int, *, ja: Sequence[np.ndarray] = (), piso: float = PISO,
             parecida: float = PARECIDA) -> list[int]:
    """As posições das ``quantas`` melhores imagens com nota a partir do ``piso``, da melhor à
    pior, sem duas parecidas demais entre si nem com as que ``ja`` foram usadas."""
    escolhidas: list[int] = []
    for i in sorted(range(len(n.notas)), key=lambda i: -n.notas[i]):
        if len(escolhidas) >= quantas or n.notas[i] < piso:
            break
        outras = [n.vetores[j] for j in escolhidas] + list(ja)
        if any(float(n.vetores[i] @ v) > parecida for v in outras):
            continue
        escolhidas.append(i)
    return escolhidas


__all__ = ["ARQUIVOS", "PARECIDA", "PISO", "REPOSITORIO", "REVISAO", "TAMANHO", "ErroDoAuditor",
           "Notas", "avaliar", "baixado", "escolher", "falso", "juntar", "lembrar", "preparar",
           "soltar"]
