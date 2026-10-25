"""
Separar um vídeo longo em cenas (o dono, 23/10/2026): a pessoa solta o vídeo e recebe a pasta
da biblioteca pronta, com os clipes e o ``cenas.json``, sem cortar nada à mão.

- **Os cortes:** cada quadro é lido pequeno (``LARGURA_DA_ANALISE`` px), em HSV, e a
  diferença média para o anterior é a "mudança" dele. Corte é o quadro que muda pelo menos
  ``MUDANCA_MINIMA`` e ``RAZAO`` vezes mais que os vizinhos (os ``JANELA`` de cada lado): o
  detector adaptativo do PySceneDetect, sem o OpenCV. Uma câmera correndo muda muito em
  vários quadros seguidos e não corta; uma troca de plano muda num quadro só.
- **O preto** (um fade, a tarja entre duas cenas) separa as cenas e fica de fora.
- **O tamanho:** a montagem toca cada cena do começo, por uns ``cenas.CENA_S``. Uma tomada
  comprida é partida em pedaços desse tamanho, para o vídeo inteiro servir; uma cena de menos
  de ``CENA_MINIMA_S`` (um clarão, um quadro solto) fica de fora.
- **Os clipes** são gravados de novo, para o corte cair no quadro certo (copiar os pacotes
  cortaria no quadro-chave): H.264 "veryfast", com o som, até 1080p.
- **A descrição** (:func:`descrever`): os pedaços de uma tomada são quase iguais, então só
  o do meio vai ao Gemini, e os outros herdam a descrição. Um vídeo de tomadas longas gasta
  bem menos pedidos da cota.

O que **não** é achado: a fusão lenta de uma cena na outra (a mudança se espalha por muitos
quadros) e o corte entre dois planos quase iguais.
"""
from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import av
import numpy as np
from PIL import Image

from editor import catalogo, cenas
from editor import saida as saida_mod
from editor import video as video_mod

#: A largura em que cada quadro é comparado (a altura segue a proporção).
LARGURA_DA_ANALISE = 96
#: Um corte muda pelo menos isto (:func:`mudanca`, de 0 a 255; parado, fica perto de 1)...
MUDANCA_MINIMA = 5.0
#: ... e esta quantidade de vezes a média dos vizinhos.
RAZAO = 3.0
JANELA = 2
#: A janela da troca espalhada por dois quadros (:func:`_pico_em_dois_quadros`).
JANELA_LARGA = 6
#: Dois cortes mais perto que isto são a mesma troca de plano: vale o primeiro. Um clarão
#: de 0,3 s ainda tem os dois cortes, e sai por ser curto (``CENA_MINIMA_S``).
ENTRE_CORTES_S = 0.12
#: Um quadro é preto quando quase tudo nele (98%) é mais escuro que isto (de 0 a 255), e o
#: preto só conta em sequência (um quadro escuro solto é uma cena de noite).
BRILHO_DO_PRETO = 32
PRETOS_SEGUIDOS = 2
#: Uma cena mais curta que isto fica de fora.
CENA_MINIMA_S = 0.6
#: O lado maior dos clipes (um vídeo 4K sai em 1080p).
LADO_MAXIMO = 1920
PRESET = "veryfast"

Progresso = Callable[[float], None]
Parar = Callable[[], bool]


@dataclass(frozen=True)
class Trecho:
    """Uma cena: de ``inicio`` a ``fim`` no vídeo longo, a ``parte`` de ``partes`` da
    ``tomada`` (o plano entre dois cortes)."""

    inicio: float
    fim: float
    tomada: int
    parte: int = 1
    partes: int = 1

    @property
    def duracao(self) -> float:
        return self.fim - self.inicio


@dataclass
class Analise:
    tempos: np.ndarray        # o instante de cada quadro
    mudancas: np.ndarray      # a mudança de cada quadro para o anterior (a do primeiro é 0)
    pretos: np.ndarray        # se o quadro é preto (só em sequência)
    duracao: float


@dataclass
class Separacao:
    pasta: Path
    #: Cada cena gravada, com o arquivo dela, na ordem do vídeo.
    clipes: list[tuple[Trecho, Path]]
    cortes: int
    tomadas: int


# ── os cortes ────────────────────────────────────────────────────────────


def _so_em_sequencia(marcas: np.ndarray, minimo: int) -> np.ndarray:
    saida = np.zeros_like(marcas)
    i, n = 0, len(marcas)
    while i < n:
        if not marcas[i]:
            i += 1
            continue
        j = i
        while j < n and marcas[j]:
            j += 1
        if j - i >= minimo:
            saida[i:j] = True
        i = j
    return saida


def mudanca(antes: np.ndarray, depois: np.ndarray) -> float:
    """A diferença entre dois quadros em HSV (0 a 255). No escuro, o matiz e a saturação
    pulam com qualquer ruído (num pixel quase preto, um nada troca a cor): a diferença do
    matiz pesa pela saturação e pelo brilho, e a da saturação, pelo brilho. Sem isso, cada
    fade virava uma fileira de cortes (medido no trailer do Sintel, 23/10/2026)."""
    a, b = antes.astype(np.float32), depois.astype(np.float32)
    v = np.minimum(a[..., 2], b[..., 2]) / 255.0
    s = np.minimum(a[..., 1], b[..., 1]) / 255.0
    dh = np.abs(a[..., 0] - b[..., 0])
    dh = np.minimum(dh, 256.0 - dh)                   # o matiz dá a volta
    ds = np.abs(a[..., 1] - b[..., 1])
    dv = np.abs(a[..., 2] - b[..., 2])
    return float((dh * s * v + ds * v + dv).mean() / 3.0)


def analisar(caminho: Path, progresso: Progresso | None = None,
             parar: Parar = lambda: False) -> Analise:
    """A mudança e o preto de cada quadro, numa leitura só do vídeo."""
    info = video_mod.sondar(caminho)
    tempos: list[float] = []
    mudancas: list[float] = []
    pretos: list[bool] = []
    anterior = None
    with av.open(str(caminho)) as c:
        fluxo = c.streams.video[0]
        fluxo.thread_type = "AUTO"
        altura = max(2, round(LARGURA_DA_ANALISE * fluxo.height / max(1, fluxo.width) / 2) * 2)
        aviso = 0.0
        for quadro in c.decode(fluxo):
            if quadro.time is None:
                continue
            if parar():
                break
            t = float(quadro.time)
            rgb = quadro.reformat(width=LARGURA_DA_ANALISE, height=altura,
                                  format="rgb24").to_ndarray()
            hsv = np.asarray(Image.fromarray(rgb).convert("HSV"), dtype=np.int16)
            mudancas.append(0.0 if anterior is None else mudanca(anterior, hsv))
            pretos.append(bool(np.percentile(hsv[..., 2], 98) < BRILHO_DO_PRETO))
            tempos.append(t)
            anterior = hsv
            if progresso and t >= aviso:
                progresso(min(1.0, t / max(info.duracao, 1e-6)))
                aviso = t + 0.5
    passo = 1 / float(info.fps or 30)
    fim = max(info.duracao, (tempos[-1] + passo) if tempos else 0.0)
    return Analise(np.array(tempos, dtype=np.float64), np.array(mudancas, dtype=np.float64),
                   _so_em_sequencia(np.array(pretos, dtype=bool), PRETOS_SEGUIDOS), fim)


def _pico_em_dois_quadros(m: np.ndarray, i: int) -> bool:
    """A troca espalhada por dois quadros (um meio-termo entre os planos): os dois mudam
    muito, um é vizinho do outro, e a regra da média não fecha. Vale o maior dos dois, se
    ficar ``RAZAO`` vezes acima da mediana de uma janela larga, sem os vizinhos."""
    if m[i] < m[i - 1] or (i + 1 < len(m) and m[i] < m[i + 1]):
        return False
    fora = np.concatenate([m[max(1, i - JANELA_LARGA):i - 1], m[i + 2:i + JANELA_LARGA + 1]])
    return len(fora) > 0 and m[i] >= RAZAO * max(float(np.median(fora)), MUDANCA_MINIMA / RAZAO)


def cortes(a: Analise) -> list[int]:
    """Os quadros onde começa um plano novo."""
    m = a.mudancas
    achados: list[int] = []
    ultimo = -math.inf
    for i in range(1, len(m)):
        if m[i] < MUDANCA_MINIMA:
            continue
        vizinhos = np.concatenate([m[max(1, i - JANELA):i], m[i + 1:i + JANELA + 1]])
        media = float(vizinhos.mean()) if len(vizinhos) else 0.0
        if media > 0 and m[i] < RAZAO * media and not _pico_em_dois_quadros(m, i):
            continue
        if a.tempos[i] - ultimo < ENTRE_CORTES_S:
            continue
        achados.append(i)
        ultimo = float(a.tempos[i])
    return achados


def planejar(a: Analise, indices: Sequence[int]) -> list[Trecho]:
    """As cenas: os planos entre os cortes, sem o preto, sem os curtos demais, e os compridos
    partidos em pedaços de uns ``cenas.CENA_S``."""
    n = len(a.tempos)
    if not n:
        return []

    def instante(i: int) -> float:
        return float(a.tempos[i]) if i < n else a.duracao

    planos: list[tuple[float, float]] = []
    for i0, i1 in zip([0, *indices], [*indices, n], strict=True):
        k = i0
        while k < i1:
            while k < i1 and a.pretos[k]:
                k += 1
            j = k
            while j < i1 and not a.pretos[j]:
                j += 1
            if j > k:
                planos.append((instante(k), instante(j)))
            k = j
    trechos: list[Trecho] = []
    tomada = 0
    for inicio, fim in planos:
        dura = fim - inicio
        if dura < CENA_MINIMA_S:
            continue
        partes = max(1, round(dura / cenas.CENA_S))
        passo = dura / partes
        for p in range(partes):
            fim_da_parte = fim if p == partes - 1 else inicio + (p + 1) * passo
            trechos.append(Trecho(round(inicio + p * passo, 4), round(fim_da_parte, 4), tomada,
                                  p + 1, partes))
        tomada += 1
    return trechos


# ── os clipes ────────────────────────────────────────────────────────────


def _par(x: float) -> int:
    return max(2, round(x / 2) * 2)


def tamanho_dos_clipes(largura: int, altura: int) -> tuple[int, int]:
    escala = min(1.0, LADO_MAXIMO / max(largura, altura, 1))
    return _par(largura * escala), _par(altura * escala)


class _Som:
    """O áudio do vídeo lido só para a frente e entregue por trecho (os trechos vêm em ordem
    e não se sobrepõem): guarda só o que ainda vai ser pedido."""

    def __init__(self, caminho: Path):
        self.c = av.open(str(caminho))
        self.quadros = self.c.decode(self.c.streams.audio[0])
        self.troca = av.AudioResampler(format="fltp", layout="stereo", rate=video_mod.TAXA)
        self.guardado = np.zeros((2, 0), dtype=np.float32)
        self.base: int | None = None          # a amostra do começo do guardado
        self.acabou = False

    def _ler(self) -> None:
        try:
            quadro = next(self.quadros)
        except (StopIteration, av.error.FFmpegError):
            saida = self.troca.resample(None)
            self.acabou = True
        else:
            if self.base is None and quadro.time is not None:
                self.base = round(float(quadro.time) * video_mod.TAXA)
            saida = self.troca.resample(quadro)
        if saida:
            self.guardado = np.concatenate([self.guardado, *(r.to_ndarray() for r in saida)],
                                           axis=1)

    def trecho(self, inicio: float, fim: float) -> np.ndarray:
        """As amostras de ``inicio`` a ``fim`` (amostras × 2), com silêncio onde faltar."""
        a, b = round(inicio * video_mod.TAXA), round(fim * video_mod.TAXA)
        while not self.acabou and (self.base is None or self.base + self.guardado.shape[1] < b):
            self._ler()
        base = self.base or 0
        saida = np.zeros((2, max(0, b - a)), dtype=np.float32)
        de, ate = max(a, base), min(b, base + self.guardado.shape[1])
        if ate > de:
            saida[:, de - a:ate - a] = self.guardado[:, de - base:ate - base]
        # o que fica para trás não é pedido de novo
        corte = min(max(0, b - base), self.guardado.shape[1])
        self.guardado = self.guardado[:, corte:]
        self.base = base + corte
        return np.ascontiguousarray(saida.T)

    def fechar(self) -> None:
        self.c.close()


def exportar(caminho: Path, trechos: Sequence[Trecho], pasta: Path, prefixo: str,
             progresso: Progresso | None = None, parar: Parar = lambda: False
             ) -> list[tuple[Trecho, Path]]:
    """Grava cada trecho num clipe da ``pasta`` (``prefixo-001.mp4``...), numa leitura só do
    vídeo. Devolve os que saíram."""
    info = video_mod.sondar(caminho)
    pasta.mkdir(parents=True, exist_ok=True)
    giro = round((info.rotacao or 0) / 90) % 4
    largura, altura = tamanho_dos_clipes(info.largura, info.altura)
    cru = (altura, largura) if giro % 2 else (largura, altura)     # antes de endireitar
    digitos = max(3, len(str(len(trechos))))
    nomes = [pasta / f"{prefixo}-{k + 1:0{digitos}d}.mp4" for k in range(len(trechos))]
    opcoes = saida_mod.OpcoesDeSaida(formato="mp4", codec="h264", qualidade="equilibrada")
    som = _Som(caminho) if info.tem_audio else None
    feitos: list[tuple[Trecho, Path]] = []
    k, gravador = 0, None
    aviso = 0.0
    try:
        with av.open(str(caminho)) as c:
            fluxo = c.streams.video[0]
            fluxo.thread_type = "AUTO"
            for quadro in c.decode(fluxo):
                if quadro.time is None:
                    continue
                if parar():
                    break
                t = float(quadro.time)
                while k < len(trechos) and t >= trechos[k].fim - 1e-6:
                    if gravador is not None:
                        gravador.fechar()
                        feitos.append((trechos[k], nomes[k]))
                        gravador = None
                    k += 1
                if k >= len(trechos):
                    break
                if t < trechos[k].inicio - 1e-6:
                    continue
                if gravador is None:
                    gravador = video_mod.Gravador(nomes[k], opcoes, largura, altura, info.fps,
                                                  com_audio=som is not None, preset=PRESET)
                    if som is not None:
                        gravador.preparar_audio(som.trecho(trechos[k].inicio, trechos[k].fim))
                matriz = quadro.reformat(width=cru[0], height=cru[1], format="rgb24").to_ndarray()
                if giro:
                    matriz = np.ascontiguousarray(np.rot90(matriz, k=giro))
                gravador.quadro(matriz)
                if progresso and t >= aviso:
                    progresso(min(1.0, t / max(info.duracao, 1e-6)))
                    aviso = t + 0.5
        if gravador is not None and not parar():
            gravador.fechar()
            feitos.append((trechos[k], nomes[k]))
            gravador = None
    finally:
        if gravador is not None:                       # interrompido: o clipe pela metade sai
            gravador.__exit__(RuntimeError, None, None)
        if som is not None:
            som.fechar()
    return feitos


# ── o vídeo inteiro ──────────────────────────────────────────────────────


def nome_curto(texto: str) -> str:
    """O nome do vídeo como pasta e prefixo dos clipes: sem acento, minúsculo, com hífens."""
    base = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")[:40].strip("-")
    return base or "cenas"


def pasta_nova(raiz: Path, nome: str) -> Path:
    """``raiz/nome``, ou ``nome-2``, ``nome-3``... se já existe."""
    base = nome_curto(nome)
    pasta, n = raiz / base, 1
    while pasta.exists():
        n += 1
        pasta = raiz / f"{base}-{n}"
    return pasta


def separar(caminho: Path, pasta: Path, progresso: Callable[[str, float], None] | None = None,
            parar: Parar = lambda: False) -> Separacao:
    """Acha os cortes e grava as cenas na ``pasta``. O ``progresso`` recebe a etapa
    ("analisando" ou "gravando") e a fração dela."""
    caminho = Path(caminho)
    a = analisar(caminho, (lambda f: progresso("analisando", f)) if progresso else None, parar)
    indices = cortes(a)
    trechos = planejar(a, indices)
    if not trechos:
        raise ValueError("não achei nenhuma cena: o vídeo é curto demais ou todo preto")
    clipes = [] if parar() else exportar(
        caminho, trechos, pasta, nome_curto(caminho.stem),
        (lambda f: progresso("gravando", f)) if progresso else None, parar)
    return Separacao(pasta, clipes, len(indices), len({t.tomada for t, _ in clipes}))


def _mmss(t: float) -> str:
    return f"{int(t // 60)}:{int(t % 60):02d}"


def descrever(sep: Separacao, *, assunto: str = "",
              progresso: catalogo.Progresso | None = None, parar: Parar = lambda: False,
              transporte=None) -> catalogo.Geracao:
    """A matriz das cenas separadas: o pedaço do meio de cada tomada vai ao Gemini (ou ao
    rascunho), e os outros pedaços dela herdam a descrição. Sem o Gemini, a descrição diz de
    onde a cena saiu no vídeo, para achar na revisão."""
    por_tomada: dict[int, list[int]] = {}
    for i, (trecho, _caminho) in enumerate(sep.clipes):
        por_tomada.setdefault(trecho.tomada, []).append(i)
    representantes = {tomada: ids[len(ids) // 2] for tomada, ids in por_tomada.items()}
    g = catalogo.gerar([(sep.clipes[i][1], sep.clipes[i][1].name)
                        for i in representantes.values()],
                       assunto=assunto, progresso=progresso, parar=parar, transporte=transporte)
    descritas = {c["arquivo"]: c for c in g.cenas}
    campos = ("descricao", "categorias", "personagens", "periodo", "energia", "monetizacao", "obs")
    saida = []
    for trecho, caminho in sep.clipes:
        modelo = descritas.get(sep.clipes[representantes[trecho.tomada]][1].name) or {}
        cena = {"id": caminho.stem, "arquivo": caminho.name,
                **{k: modelo[k] for k in campos if k in modelo},
                "duracao": round(trecho.duracao, 3)}
        if g.por == "rascunho" or not cena.get("descricao"):
            de, ate = _mmss(trecho.inicio), _mmss(trecho.fim)
            cena.update(descricao=f"Trecho de {de} a {ate} do vídeo", obs="descreva esta cena")
        cena.setdefault("monetizacao", "ok")
        saida.append(cena)
    aviso = g.aviso
    if g.por == "rascunho":
        aviso = ("sem a chave do Gemini, cada cena diz de onde saiu no vídeo: descreva na "
                 "tabela")
    return catalogo.Geracao(saida, g.por, aviso, g.pedidos)


__all__ = ["Analise", "Separacao", "Trecho", "analisar", "cortes", "descrever", "exportar",
           "nome_curto", "pasta_nova", "planejar", "separar", "tamanho_dos_clipes"]
