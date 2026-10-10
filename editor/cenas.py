"""
A biblioteca de cenas: o fundo da montagem feito de vários clipes, escolhidos pelo que
é dito.

No vídeo de referência, um trailer foi cortado em 128 cenas de ~2 s, descritas num
catálogo (``cenas.json``), e cada bloco do roteiro tocava as cenas que combinavam com
ele. Aqui a pessoa traz a pasta das cenas e o catálogo (a "matriz"), e quem escolhe é o
Gemini (:mod:`editor.roteiro`) ou, sem ele, as palavras.

**As cenas são vídeos ou fotos.** Uma foto vale por uma cena de ``FOTO_S`` e ganha um
movimento lento (aproxima ou afasta um pouco, andando de lado), para não ficar parada.

**O tamanho:** cada cena é entregue no tamanho de quem pede (o quadro do vídeo, ou a
janela 16:9). Se a forma for muito diferente (uma foto em pé num vídeo deitado), ela
entra inteira, sobre ela mesma desfocada, em vez de perder metade no corte.

**A matriz** é uma lista (ou ``{"cenas": [...]}``) com, por cena:

- ``arquivo`` (obrigatório): o clipe, casado pelo nome do arquivo com o que veio na pasta;
- ``descricao`` (obrigatória): o que aparece;
- opcionais, que ajudam a escolha: ``id``, ``categorias``, ``personagens``, ``periodo``,
  ``energia`` (baixa, media, alta), ``monetizacao`` (ok, cuidado, evitar) e ``obs``.

Cena marcada "evitar" nunca entra.
"""
from __future__ import annotations

import bisect
import functools
import json
import math
import re
import unicodedata
from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter, ImageOps

from editor import video as video_mod
from editor.transcricao import Palavra

#: Os vídeos e as fotos que a biblioteca aceita.
VIDEOS = (".mp4", ".mov", ".m4v", ".webm", ".mkv")
IMAGENS = (".jpg", ".jpeg", ".png", ".webp")
EXTENSOES = VIDEOS + IMAGENS
#: Uma foto vale por uma cena deste tamanho, e aproxima (ou afasta) 8% enquanto toca.
FOTO_S = 3.0
FOTO_ZOOM = 0.08
#: Mais diferente que isto (a proporção de uma pela da outra), a cena entra inteira, sobre
#: ela mesma desfocada, em vez de cortada.
DIFERENCA_PARA_ENCAIXAR = 1.45
#: Um bloco de fala dura de 2 a 6 s; uma cena, uns 2 s.
BLOCO_MINIMO_S = 2.0
BLOCO_MAXIMO_S = 6.0
CENA_S = 2.2
#: Uma pausa maior que isto também fecha um bloco.
PAUSA_DO_BLOCO_S = 0.6
#: No máximo esta quantidade de cenas "cuidado" por vídeo.
CUIDADO_MAXIMO = 2
#: O corte para um quadro antes do fim da cena, para não pegar a próxima tomada do trailer.
SOBRA_S = 1 / 30
#: O tamanho em que as cenas são entregues (16:9, cortadas para cobrir).
TAMANHO = (1280, 720)

ENERGIAS = ("baixa", "media", "alta")
MONETIZACOES = ("ok", "cuidado", "evitar")


class MatrizInvalida(ValueError):
    """A matriz não é uma lista de cenas com arquivo e descrição."""


@dataclass
class Cena:
    id: str
    arquivo: Path
    descricao: str
    categorias: list[str] = field(default_factory=list)
    personagens: list[str] = field(default_factory=list)
    periodo: str = ""
    energia: str = ""
    monetizacao: str = "ok"
    obs: str = ""
    duracao: float = 0.0
    largura: int = 0
    altura: int = 0
    rotacao: int = 0
    #: "video" ou "imagem".
    tipo: str = "video"

    @property
    def imagem(self) -> bool:
        return self.tipo == "imagem"

    def linha(self) -> str:
        """A cena numa linha, para o pedido do Gemini."""
        partes = [self.id, self.descricao]
        if self.categorias:
            partes.append("categorias: " + ", ".join(self.categorias))
        if self.personagens:
            partes.append("personagens: " + ", ".join(self.personagens))
        for rotulo, valor in (("período", self.periodo), ("energia", self.energia),
                              ("monetização", self.monetizacao), ("obs", self.obs)):
            if valor:
                partes.append(f"{rotulo}: {valor}")
        partes.append("foto" if self.imagem else f"{self.duracao:.1f} s")
        return " | ".join(partes)


@dataclass
class Biblioteca:
    #: As cenas que podem entrar (com clipe, sem as "evitar").
    cenas: list[Cena]
    evitadas: int = 0
    #: Entradas da matriz cujo clipe não veio na pasta.
    sem_clipe: list[str] = field(default_factory=list)
    #: Clipes da pasta que a matriz não descreve.
    sem_descricao: list[str] = field(default_factory=list)

    @property
    def duracao(self) -> float:
        return sum(c.duracao for c in self.cenas)

    def por_id(self) -> dict[str, Cena]:
        return {c.id: c for c in self.cenas}

    def ficha(self) -> dict:
        return {"cenas": len(self.cenas), "duracao": round(self.duracao, 1),
                "fotos": sum(c.imagem for c in self.cenas),
                "evitadas": self.evitadas, "sem_clipe": self.sem_clipe[:20],
                "sem_descricao": self.sem_descricao[:20]}

    def em_pe(self) -> bool:
        """Se a maior parte das cenas é em pé (o vídeo sai em pé, sem outra escolha)."""
        return sum(c.altura > c.largura for c in self.cenas) * 2 > len(self.cenas)


def e_imagem(caminho: Path | str) -> bool:
    return Path(caminho).suffix.lower() in IMAGENS


@functools.lru_cache(maxsize=6)
def ler_imagem(caminho: str) -> np.ndarray:
    """A foto em RGB, já endireitada pela orientação que a câmera gravou (EXIF)."""
    with Image.open(caminho) as im:
        return np.asarray(ImageOps.exif_transpose(im).convert("RGB"))


def medir_imagem(caminho: Path) -> tuple[int, int]:
    with Image.open(caminho) as im:
        largura, altura = im.size
        orientacao = im.getexif().get(0x0112, 1)
    return (altura, largura) if orientacao in (5, 6, 7, 8) else (largura, altura)


def clipes_da_pasta(pasta: Path) -> list[Path]:
    """Os vídeos e as fotos de uma pasta e das subpastas."""
    return sorted(p for p in Path(pasta).rglob("*")
                  if p.is_file() and p.suffix.lower() in EXTENSOES
                  and not p.name.startswith("."))


def _lista(valor) -> list[str]:
    if isinstance(valor, str):
        return [v.strip() for v in valor.split(",") if v.strip()]
    if isinstance(valor, list):
        return [str(v).strip() for v in valor if str(v).strip()]
    return []


def ler_matriz(dados: str | bytes | list | dict, clipes: Sequence[Path]) -> Biblioteca:
    """A biblioteca a partir da matriz (o texto do JSON, ou já lido) e dos clipes que
    vieram. Mede cada clipe (duração e tamanho)."""
    if isinstance(dados, (str, bytes)):
        try:
            dados = json.loads(dados)
        except json.JSONDecodeError as erro:
            raise MatrizInvalida(f"a matriz não é um JSON válido: {erro.msg} "
                                 f"(linha {erro.lineno})") from erro
    lista = dados.get("cenas") if isinstance(dados, dict) else dados
    if not isinstance(lista, list) or not lista:
        raise MatrizInvalida("a matriz precisa ser uma lista de cenas (ou "
                             '{"cenas": [...]}), como o cenas.json')
    por_nome = {Path(c).name.lower(): Path(c) for c in clipes}
    usados: set[str] = set()
    cenas, evitadas, sem_clipe = [], 0, []
    for k, item in enumerate(lista):
        if not isinstance(item, dict) or not item.get("arquivo") or not item.get("descricao"):
            raise MatrizInvalida(f"a cena {k + 1} da matriz não tem "
                                 '"arquivo" e "descricao"')
        nome = Path(str(item["arquivo"]).replace("\\", "/")).name.lower()
        caminho = por_nome.get(nome)
        ident = str(item.get("id") or Path(nome).stem)
        if caminho is None:
            sem_clipe.append(ident)
            continue
        usados.add(nome)
        monetizacao = str(item.get("monetizacao", "ok")).strip().lower() or "ok"
        if monetizacao == "evitar":
            evitadas += 1
            continue
        try:
            if e_imagem(caminho):
                largura, altura = medir_imagem(caminho)
                duracao, rotacao, tipo = FOTO_S, 0, "imagem"
            else:
                info = video_mod.sondar(caminho)
                largura, altura, rotacao, tipo = info.largura, info.altura, info.rotacao, "video"
                duracao = info.duracao
        except Exception:
            sem_clipe.append(ident)
            continue
        if duracao <= 0.2:
            continue
        energia = str(item.get("energia", "")).strip().lower()
        cenas.append(Cena(
            id=ident, arquivo=caminho, descricao=str(item["descricao"]).strip(),
            categorias=_lista(item.get("categorias")),
            personagens=_lista(item.get("personagens")),
            periodo=str(item.get("periodo", "")).strip(),
            energia=energia if energia in ENERGIAS else "",
            monetizacao=monetizacao if monetizacao in MONETIZACOES else "ok",
            obs=str(item.get("obs", "")).strip(), duracao=round(duracao, 3),
            largura=largura, altura=altura, rotacao=rotacao, tipo=tipo))
    sem_descricao = sorted(Path(c).name for n, c in por_nome.items() if n not in usados)
    if not cenas:
        raise MatrizInvalida("nenhuma cena da matriz casou com os clipes da pasta "
                             "(o nome do arquivo precisa ser o mesmo)")
    return Biblioteca(cenas, evitadas, sem_clipe, sem_descricao)


# ── os blocos da fala ────────────────────────────────────────────────────


@dataclass
class BlocoDeFala:
    inicio: float
    fim: float
    #: As palavras do bloco: da ``primeira`` à ``ultima`` (índices na fala).
    primeira: int
    ultima: int
    texto: str

    @property
    def duracao(self) -> float:
        return self.fim - self.inicio


def blocos_da_fala(palavras: Sequence[Palavra], duracao: float) -> list[BlocoDeFala]:
    """A fala em blocos de 2 a 6 s, fechados no fim das frases ou nas pausas. Os blocos
    cobrem o vídeo inteiro, do zero à ``duracao``."""
    if not palavras:
        return [BlocoDeFala(0.0, duracao, 0, -1, "")] if duracao > 0 else []
    grupos: list[list[int]] = [[]]
    for i, w in enumerate(palavras):
        atual = grupos[-1]
        if atual:
            comeco = palavras[atual[0]].inicio
            longo = w.fim - comeco > BLOCO_MAXIMO_S
            pausa = w.inicio - palavras[atual[-1]].fim > PAUSA_DO_BLOCO_S
            if longo or (pausa and palavras[atual[-1]].fim - comeco >= BLOCO_MINIMO_S):
                grupos.append([])
                atual = grupos[-1]
        atual.append(i)
        fecha = w.texto.rstrip().endswith((".", "!", "?", "…"))
        if fecha and w.fim - palavras[atual[0]].inicio >= BLOCO_MINIMO_S:
            grupos.append([])
    grupos = [g for g in grupos if g]
    # um último bloco curto demais vai para o anterior
    if len(grupos) > 1 and palavras[grupos[-1][-1]].fim - palavras[grupos[-1][0]].inicio \
            < BLOCO_MINIMO_S:
        grupos[-2].extend(grupos.pop())
    blocos = []
    for k, g in enumerate(grupos):
        inicio = 0.0 if k == 0 else palavras[g[0]].inicio
        fim = duracao if k == len(grupos) - 1 else palavras[grupos[k + 1][0]].inicio
        texto = " ".join(palavras[i].texto for i in g)
        blocos.append(BlocoDeFala(round(inicio, 3), round(max(fim, inicio + 0.1), 3), g[0],
                                  g[-1], texto))
    return blocos


def cenas_por_bloco(bloco: BlocoDeFala) -> int:
    """Quantas cenas um bloco pede: uma a cada ~2 s."""
    return max(1, math.ceil(bloco.duracao / CENA_S))


# ── a escolha pelas palavras (sem o Gemini) ──────────────────────────────


def _nua(texto: str) -> str:
    base = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in base if not unicodedata.combining(c))


def _termos(texto: str) -> set[str]:
    """As palavras de um texto, sem acento e no singular, só as que dizem algo."""
    from editor.plano import VAZIAS, _formas

    termos = set()
    for w in re.findall(r"[a-z0-9]+", _nua(texto)):
        if len(w) < 4 or w in VAZIAS:
            continue
        termos.update(_formas(w))
    return termos


def escolher_por_palavras(blocos: Sequence[BlocoDeFala], biblioteca: Biblioteca
                          ) -> list[list[str]]:
    """As cenas de cada bloco, casando as palavras dele com a descrição, as categorias,
    os personagens e as observações de cada cena. Sem repetir cena; desempate pela
    energia (o primeiro bloco, o gancho, pede cena forte); sem casamento, as cenas "ok"
    ainda não usadas, em rodízio."""
    termos_da_cena = {c.id: _termos(" ".join([c.descricao, *c.categorias, *c.personagens,
                                               c.obs])) for c in biblioteca.cenas}
    usadas: set[str] = set()
    cuidado = 0
    escolhas: list[list[str]] = []
    reserva = [c for c in biblioteca.cenas if c.monetizacao == "ok"]
    vez = 0
    for k, bloco in enumerate(blocos):
        termos = _termos(bloco.texto)
        quer_forte = k == 0

        def nota(c: Cena, termos=termos, quer_forte=quer_forte) -> tuple:
            casam = len(termos & termos_da_cena[c.id])
            energia = ENERGIAS.index(c.energia) if c.energia in ENERGIAS else 1
            return (casam, energia if quer_forte else 0, -biblioteca.cenas.index(c))

        precisa = cenas_por_bloco(bloco)
        candidatas = sorted((c for c in biblioteca.cenas if c.id not in usadas),
                            key=nota, reverse=True)
        escolhidas: list[str] = []
        for c in candidatas:
            if len(escolhidas) >= precisa or nota(c)[0] == 0:
                break
            if c.monetizacao == "cuidado":
                if cuidado >= CUIDADO_MAXIMO:
                    continue
                cuidado += 1
            escolhidas.append(c.id)
            usadas.add(c.id)
        if len(escolhidas) < precisa and reserva:
            livres = [c for c in reserva if c.id not in usadas]
            if not livres:                  # todas já tocaram: repetem, em rodízio
                livres = reserva[vez % len(reserva):] + reserva[:vez % len(reserva)]
                vez += 1
            if quer_forte:                  # o gancho sem casamento ainda pede cena forte
                livres = sorted(livres, key=lambda c: c.energia != "alta")
            for c in livres[:precisa - len(escolhidas)]:
                escolhidas.append(c.id)
                usadas.add(c.id)
        if quer_forte and escolhidas:
            fortes = [i for i in escolhidas
                      if biblioteca.por_id()[i].energia == "alta"]
            escolhidas = fortes + [i for i in escolhidas if i not in fortes]
        escolhas.append(escolhidas or [biblioteca.cenas[k % len(biblioteca.cenas)].id])
    return escolhas


# ── a trilha ─────────────────────────────────────────────────────────────


@dataclass
class Corte:
    """Um pedaço da trilha: a cena tocando de ``desde`` em diante, de ``inicio`` a
    ``fim`` (no tempo do vídeo editado)."""

    inicio: float
    fim: float
    cena: Cena
    desde: float = 0.0
    bloco: int = 0


def montar_trilha(blocos: Sequence[BlocoDeFala], escolhas: Sequence[Sequence[str]],
                  biblioteca: Biblioteca) -> list[Corte]:
    """As cenas de cada bloco em ordem, até o bloco seguinte; se faltar cena, elas
    repetem em vez de congelar."""
    por_id = biblioteca.por_id()
    cortes: list[Corte] = []
    for k, (bloco, ids) in enumerate(zip(blocos, escolhas, strict=True)):
        cenas = [por_id[i] for i in ids if i in por_id] or [biblioteca.cenas[0]]
        t, i = bloco.inicio, 0
        while t < bloco.fim - 1e-3:
            cena = cenas[i % len(cenas)]
            dura = max(0.3, cena.duracao - SOBRA_S)
            fim = min(bloco.fim, t + dura)
            cortes.append(Corte(round(t, 3), round(fim, 3), cena, 0.0, k))
            t, i = fim, i + 1
    return cortes


def sincronizar(cortes: Sequence[Corte], fontes: Sequence[tuple[Path, float, float, float]],
                linha, biblioteca: Biblioteca) -> list[Corte]:
    """Os vídeos de onde vem o som, quando o roteiro os escolhe, entram no ponto da fala:
    a boca de quem fala bate com a voz. Escolhido fora do trecho dele, entra o vídeo de
    quem está falando naquele momento (um rosto falando outra coisa parece defeito).

    ``fontes``: (o arquivo, onde ele começa no áudio, o que foi aparado do começo, quanto
    dura); ``linha``: a linha dos cortes (um corte de silêncio emenda dois pedaços da fala,
    então a cena é partida ali, e cada pedaço pega o seu ponto)."""
    por_arquivo = {Path(c.arquivo).resolve(): c for c in biblioteca.cenas}
    das_fontes = [(Path(a).resolve(), ini, aparado, dura) for a, ini, aparado, dura in fontes]
    arquivos = {a for a, *_ in das_fontes}
    if not arquivos & set(por_arquivo):
        return list(cortes)
    fronteiras = linha.fronteiras()
    saida: list[Corte] = []
    for c in cortes:
        if Path(c.cena.arquivo).resolve() not in arquivos:
            saida.append(c)
            continue
        dentro = [f for f in fronteiras if c.inicio < f < c.fim]
        for a, b in zip([c.inicio, *dentro], [*dentro, c.fim], strict=True):
            t0 = linha.para_origem(a)
            falando = next(((arq, ini, aparado) for arq, ini, aparado, dura in das_fontes
                            if ini <= t0 < ini + dura and arq in por_arquivo), None)
            pedaco = Corte(round(a, 3), round(b, 3), c.cena, c.desde, c.bloco)
            if falando is not None:
                arq, ini, aparado = falando
                desde = aparado + (t0 - ini)
                if desde < por_arquivo[arq].duracao - SOBRA_S:
                    pedaco = Corte(round(a, 3), round(b, 3), por_arquivo[arq], round(desde, 3),
                                   c.bloco)
            saida.append(pedaco)
    return saida


class FundoDeCenas:
    """A trilha de cenas com a cara de um ``video.Cursor``: ``em(t)`` devolve o quadro
    do instante ``t`` do vídeo editado, em 16:9, cortado para cobrir."""

    def __init__(self, cortes: Sequence[Corte], tamanho: tuple[int, int] = TAMANHO):
        self.cortes = list(cortes)
        self.inicios = [c.inicio for c in self.cortes]
        self.largura, self.altura = tamanho
        self._cursores: OrderedDict[Path, video_mod.Cursor] = OrderedDict()

    def corte_em(self, t: float) -> Corte | None:
        if not self.cortes:
            return None
        k = max(0, bisect.bisect_right(self.inicios, t) - 1)
        return self.cortes[k]

    def _cursor(self, cena: Cena) -> video_mod.Cursor:
        cursor = self._cursores.get(cena.arquivo)
        if cursor is None:
            cursor = video_mod.Cursor(cena.arquivo, cena.rotacao, duracao=cena.duracao)
            self._cursores[cena.arquivo] = cursor
            while len(self._cursores) > 4:
                self._cursores.popitem(last=False)
        else:
            self._cursores.move_to_end(cena.arquivo)
        return cursor

    def em(self, t: float) -> np.ndarray | None:
        corte = self.corte_em(t)
        if corte is None:
            return None
        if corte.cena.imagem:
            return self._foto(corte, t)
        local = min(corte.cena.duracao - SOBRA_S, corte.desde + max(0.0, t - corte.inicio))
        q = self._cursor(corte.cena).em(max(0.0, local))
        if q is None:
            return None
        return ajustar(q, self.largura, self.altura)

    @functools.lru_cache(maxsize=4)  # noqa: B019 (poucas fotos por vez, e o fundo vive pouco)
    def _base(self, caminho: Path) -> np.ndarray:
        return ajustar(ler_imagem(str(caminho)), self.largura, self.altura)

    def _foto(self, corte: Corte, t: float) -> np.ndarray:
        """A foto com o movimento lento: aproxima nos cortes pares e afasta nos ímpares,
        andando um pouco de lado."""
        base = self._base(corte.cena.arquivo)
        f = min(1.0, max(0.0, (t - corte.inicio) / max(0.1, corte.fim - corte.inicio)))
        k = self.cortes.index(corte) if corte in self.cortes else 0
        zoom = 1 + FOTO_ZOOM * (f if k % 2 == 0 else 1 - f)
        cw, ch = self.largura / zoom, self.altura / zoom
        lado = (f - 0.5) * (1 if k % 4 < 2 else -1)
        x0 = (self.largura - cw) / 2 + lado * (self.largura - cw) * 0.8
        y0 = (self.altura - ch) / 2
        img = Image.fromarray(base).resize((self.largura, self.altura), Image.BILINEAR,
                                           box=(x0, y0, x0 + cw, y0 + ch))
        return np.asarray(img)


def cobrir(q: np.ndarray, largura: int, altura: int) -> np.ndarray:
    """O quadro cortado e redimensionado para cobrir ``largura`` × ``altura``."""
    h, w = q.shape[:2]
    if (w, h) == (largura, altura):
        return q
    escala = max(largura / w, altura / h)
    cw, ch = largura / escala, altura / escala
    x0, y0 = (w - cw) / 2, (h - ch) / 2
    img = Image.fromarray(q).resize((largura, altura), Image.BILINEAR,
                                    box=(x0, y0, x0 + cw, y0 + ch))
    return np.asarray(img)


def ajustar(q: np.ndarray, largura: int, altura: int) -> np.ndarray:
    """O quadro no tamanho pedido: cobrindo, se a forma é parecida; inteiro, sobre ele
    mesmo desfocado, se é muito diferente (uma foto em pé num vídeo deitado)."""
    h, w = q.shape[:2]
    proporcao = (w / h) / (largura / altura)
    if max(proporcao, 1 / proporcao) < DIFERENCA_PARA_ENCAIXAR:
        return cobrir(q, largura, altura)
    fundo = Image.fromarray(cobrir(q, largura // 4, altura // 4)).filter(
        ImageFilter.GaussianBlur(6)).resize((largura, altura), Image.BILINEAR)
    escala = min(largura / w, altura / h)
    tw, th = max(1, round(w * escala)), max(1, round(h * escala))
    fundo.paste(Image.fromarray(q).resize((tw, th), Image.BILINEAR),
                ((largura - tw) // 2, (altura - th) // 2))
    return np.asarray(fundo)


__all__ = ["EXTENSOES", "IMAGENS", "VIDEOS", "Biblioteca", "BlocoDeFala", "Cena", "Corte",
           "FundoDeCenas", "MatrizInvalida", "ajustar", "blocos_da_fala", "cenas_por_bloco",
           "clipes_da_pasta", "cobrir", "e_imagem", "escolher_por_palavras", "ler_imagem",
           "ler_matriz", "medir_imagem", "montar_trilha", "sincronizar"]
