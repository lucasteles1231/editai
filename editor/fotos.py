"""
As fotos achadas pelo que é dito (o vídeo só pelo tema). Sem vídeo e sem cenas, o roteiro vira
uma biblioteca de cenas de fotos, com a licença de cada uma conferida e os créditos ao lado.

1. **Os blocos:** o roteiro é partido nos trechos em que a imagem muda (os parágrafos dele, e
   os longos nas frases).
2. **As buscas:** a IA escreve, num pedido só, a busca de cada bloco em inglês (o que mostrar,
   concreto), uma busca de reserva (mais ampla) e uma descrição curta em português (que o
   roteiro do vídeo lê para escolher a foto de cada trecho). Sem a IA, a busca é o próprio
   bloco, sem as palavras vazias.
3. **As fontes:**
   - **o Pexels**, com a chave de quem usa (fotos de uso livre);
   - **o Openverse**, sem chave, só com as licenças que deixam pôr a foto num vídeo sem pedir:
     CC0, domínio público e CC BY (que pede o crédito). A BY-SA (que obrigaria o vídeo à mesma
     licença), a NC e a ND ficam de fora.
4. **A triagem pelo texto:** saem a foto pequena (menos de ``LADO_MINIMO`` no lado maior), a
   que é texto, logo, diagrama ou captura de tela pelo título e pelas etiquetas, e a repetida.
5. **O auditor** (:mod:`editor.auditor`): as primeiras de cada busca ganham uma nota contra a
   descrição do trecho, e ficam as que mais combinam, sem repetir uma cena já posta. Antes,
   ficavam as 2 primeiras da busca, e o banco de fotos devolve de tudo: no vídeo do GPS, uma
   aranha no lugar de um satélite e ciclistas no lugar de "um satélite em movimento". Nenhuma
   passando do piso, vem a busca de reserva. Sem o auditor (``conferir=False``, ou sem internet
   na primeira vez), ficam as primeiras, como antes.
6. **A pasta:** ``Filmes/editor-de-video/fotos/<tema>``, com as fotos, o ``cenas.json`` (a
   descrição de cada uma) e o ``creditos.txt``, para colar na descrição do vídeo.
7. **O bloco sem foto** fica sem: as fotos dos vizinhos cobrem o trecho.

Para os testes há as fotos falsas (``EDITOR_FOTOS=falso``): gradientes desenhados aqui, sem
rede, e uma IA falsa que devolve a busca pelo próprio bloco.
"""
from __future__ import annotations

import bisect
import difflib
import io
import json
import logging
import os
import re
import threading
import time
import unicodedata
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from editor import auditor, ia, pexels

logger = logging.getLogger(__name__)

OPENVERSE = "https://api.openverse.org/v1/images/"
VARIAVEL_FALSA = "EDITOR_FOTOS"
#: As licenças que deixam pôr a foto num vídeo sem pedir (a CC BY pede o crédito).
LICENCAS = ("cc0", "pdm", "by")
NOMES_DAS_LICENCAS = {"cc0": "CC0", "pdm": "domínio público", "by": "CC BY"}
#: Quantas fotos por bloco, o lado mínimo e o lado em que ficam guardadas.
POR_BLOCO = 2
LADO_MINIMO = 1000
LADO_GUARDADO = 1920
#: Um bloco tem até tantas palavras (uns 8 s de fala): maior que isso, parte nas frases.
PALAVRAS_POR_BLOCO = 22
#: Menos palavras que isto no fim de um parágrafo partido: fica com o trecho de antes.
RABO_CURTO = 8
#: As palavras do título ou das etiquetas que denunciam uma imagem que não serve de fundo.
NAO_SERVE = ("logo", "logotipo", "text", "texto", "diagram", "diagrama", "screenshot",
             "captura", "infographic", "infográfico", "chart", "gráfico", "map of", "poster",
             "cartaz", "meme", "icon", "ícone", "clipart", "vector", "vetor")
#: O intervalo mínimo entre dois pedidos ao Openverse: o anônimo pode 20 por minuto e 200 por
#: dia (os cabeçalhos dele, lidos em 25/10/2026).
ENTRE_PEDIDOS_S = 3.0
#: Quantas candidatas de cada busca o auditor confere. As do Pexels vão pela prévia (uns
#: 40 KB); com as 12 da página, a nota média das 2 escolhidas subiu de 0,109 (com 4) para
#: 0,132. As do Openverse vêm inteiras (a prévia dele falha e tem limite por dia), por isso
#: menos.
CONFERIDAS = 12
CONFERIDAS_INTEIRAS = 6
#: Quantas baixam ao mesmo tempo.
DE_UMA_VEZ = 4
AGENTE = "Editai (https://github.com/lucasteles1231/editai)"

SISTEMA = """Você escolhe fotos de banco de imagens para o fundo de um vídeo de explicação.
Para cada trecho da narração, diga o que mostrar numa foto de verdade. Responda só com o JSON
pedido."""

Progresso = Callable[[str, int, int], None]


class SemFotos(RuntimeError):
    """Não deu para achar as fotos (a mensagem diz por quê)."""


@dataclass
class Busca:
    bloco: str
    termo: str              # em inglês, para as fontes
    descricao: str          # em português, para a matriz
    #: Outra busca, mais ampla, para quando a primeira não achar uma foto que mostre o trecho.
    reserva: str = ""
    #: O que a foto tem de mostrar, para o auditor: a descrição que a IA imaginou ou, sem ela,
    #: a própria busca (o trecho falado dava nota baixa até para a foto certa).
    alvo: str = ""

    def __post_init__(self) -> None:
        self.alvo = self.alvo or self.termo


@dataclass
class Achada:
    """Uma foto achada, antes de baixar."""

    url: str
    titulo: str
    autor: str
    licenca: str            # "cc0", "pdm", "by" ou "pexels"
    versao: str
    link: str               # a página da foto (para o crédito)
    licenca_url: str
    fonte: str              # "Openverse (Flickr)", "Pexels"…
    largura: int = 0
    altura: int = 0
    pexels_id: int | None = None

    def credito(self) -> str:
        if self.licenca == "pexels":
            return f"Foto de {self.autor or 'autor desconhecido'} no Pexels ({self.link})"
        nome = NOMES_DAS_LICENCAS.get(self.licenca, self.licenca.upper())
        versao = f" {self.versao}" if self.versao and self.licenca == "by" else ""
        titulo = f"\"{self.titulo}\"" if self.titulo else "Foto"
        autor = f" por {self.autor}" if self.autor else ""
        url = f" ({self.licenca_url})" if self.licenca_url else ""
        return f"{titulo}{autor}, {nome}{versao}{url}, em {self.link or self.url}"


@dataclass
class Achado:
    pasta: Path
    cenas: list[dict] = field(default_factory=list)
    creditos: list[str] = field(default_factory=list)
    #: Os blocos que ficaram sem foto (o índice, a partir de 0).
    sem_foto: list[int] = field(default_factory=list)
    pedidos: int = 0
    #: Se o auditor escolheu as fotos, quantas candidatas ele olhou e quantas não mostravam o
    #: trecho (abaixo do piso).
    conferidas: bool = False
    olhadas: int = 0
    recusadas: int = 0
    #: O que a pessoa precisa saber (o auditor que não carregou, por exemplo).
    aviso: str = ""

    def resumo(self) -> str:
        """O que o auditor fez, numa frase, e o aviso, se houver."""
        partes = []
        if self.conferidas:
            fora = f" ({self.recusadas} não mostravam o trecho)" if self.recusadas else ""
            partes.append(f"O auditor olhou {self.olhadas} fotos{fora} e ficou com as que mais "
                          "combinam com cada trecho.")
        if self.aviso:
            partes.append(self.aviso)
        return " ".join(partes)


def falso() -> bool:
    return os.environ.get(VARIAVEL_FALSA, "").strip().lower() == "falso"


# ── os blocos e as buscas ────────────────────────────────────────────────


def blocos(roteiro: str) -> list[str]:
    """Os trechos em que a imagem muda: os parágrafos, e os longos partidos nas frases."""
    saida = []
    for paragrafo in re.split(r"\n\s*\n", str(roteiro or "").strip()):
        texto = re.sub(r"\s+", " ", paragrafo).strip()
        if not texto:
            continue
        frases = [f for f in re.split(r"(?<=[.!?…])\s+", texto) if f]
        partes: list[str] = []
        atual = ""
        for f in frases:
            if atual and len((atual + " " + f).split()) > PALAVRAS_POR_BLOCO:
                partes.append(atual)
                atual = f
            else:
                atual = f"{atual} {f}".strip()
        if atual:
            # um rabo curto ("E você, já tinha reparado?") não pede uma foto só dele
            if partes and len(atual.split()) < RABO_CURTO:
                partes[-1] += f" {atual}"
            else:
                partes.append(atual)
        saida += partes
    return saida


_VAZIAS = frozenset(re.findall(r"\S+", """
a o as os um uma uns umas de da do das dos e é em no na nos nas que se por para com sem
mais menos muito muita como quando onde porque por que isso isto essa esse
ela ele eles elas você vocês a gente já não sim também só ainda até sobre entre seu sua seus
suas meu minha ao aos à às pelo pela pelos pelas foi ser são era tem têm vai vão está estão
lá aqui ali então mas ou nem cada todo toda todos todas qual quais quem"""))


def _sem_acento(texto: str) -> str:
    base = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in base if not unicodedata.combining(c))


def termo_pelas_palavras(bloco: str) -> str:
    """A busca sem a IA: as palavras com sentido do bloco, as mais longas primeiro."""
    palavras = [w.strip(".,;:!?\"'()…").lower() for w in bloco.split()]
    boas = [w for w in palavras if len(w) > 3 and w not in _VAZIAS]
    vistas: list[str] = []
    for w in sorted(boas, key=len, reverse=True):
        if w not in vistas:
            vistas.append(w)
    return " ".join(vistas[:4]) or bloco[:40]


def esquema() -> dict:
    item = {"type": "object", "properties": {
        "k": {"type": "integer"}, "busca": {"type": "string"}, "reserva": {"type": "string"},
        "descricao": {"type": "string"}}, "required": ["k", "busca", "reserva", "descricao"]}
    return {"type": "object", "properties": {"fotos": {"type": "array", "items": item}},
            "required": ["fotos"]}


def montar_pedido(blocos_: Sequence[str], tema: str) -> str:
    linhas = "\n".join(f"- trecho {k}: {b}" for k, b in enumerate(blocos_))
    sobre = f"O tema do vídeo: {tema}\n\n" if tema else ""
    return f"""{sobre}Os trechos da narração, na ordem:
{linhas}

Para cada trecho ("k" é o número dele), devolva:
- busca: o que mostrar, em inglês, em 2 a 4 palavras concretas que um banco de fotos acha
  (objetos, lugares, pessoas fazendo algo: "rocket launch", "wifi router on desk"). Nada de
  ideia abstrata, nada de texto, nada de nome de marca.
- reserva: outra busca em inglês, mais simples e mais ampla (1 ou 2 palavras: "rocket",
  "router"), para quando a primeira não achar uma foto boa.
- descricao: a foto que você imaginou, em português, numa frase curta."""


def buscas(blocos_: Sequence[str], tema: str = "", *, transporte=None) -> tuple[list[Busca], int]:
    """A busca de cada bloco, pela IA (um pedido) ou, sem ela, pelas palavras. Devolve as
    buscas e quantos pedidos foram feitos."""
    pelas_palavras = [Busca(b, termo_pelas_palavras(b), b[:120]) for b in blocos_]
    if falso() or ia.falsa() or not ia.ligada() or not blocos_:
        return pelas_palavras, 0
    gasto: list[str] = []
    try:
        resposta, _modelo = ia.perguntar_json(SISTEMA, montar_pedido(blocos_, tema), esquema(),
                                              temperatura=0.4, transporte=transporte,
                                              gasto=gasto, leve=True)
    except ia.ErroDaIA as erro:
        logger.info("as buscas das fotos saíram pelas palavras: %s", erro)
        return pelas_palavras, len(gasto)
    saida = list(pelas_palavras)
    for item in resposta.get("fotos") or []:
        k = item.get("k") if isinstance(item, dict) else None
        if not isinstance(k, int) or isinstance(k, bool) or not 0 <= k < len(blocos_):
            continue
        termo = re.sub(r"\s+", " ", str(item.get("busca") or "")).strip()[:60]
        reserva = re.sub(r"\s+", " ", str(item.get("reserva") or "")).strip()[:40]
        descricao = re.sub(r"\s+", " ", str(item.get("descricao") or "")).strip()[:140]
        if termo:
            saida[k] = Busca(blocos_[k], termo, descricao or saida[k].descricao,
                             reserva=reserva if reserva.lower() != termo.lower() else "",
                             alvo=descricao)
    return saida, len(gasto)


# ── as fontes ────────────────────────────────────────────────────────────


def _nao_serve(*textos: str) -> bool:
    # palavra inteira: "text" não pode derrubar "texture", nem "icon", "iconic"
    junto = _sem_acento(" ".join(textos))
    return any(re.search(rf"(?<!\w){re.escape(_sem_acento(p))}(?!\w)", junto) for p in NAO_SERVE)


_vez_do_openverse = threading.Lock()
_ultimo_openverse = 0.0


def _esperar_a_vez() -> None:
    """Segura o pedido até passar ``ENTRE_PEDIDOS_S`` do anterior (as buscas correm juntas)."""
    global _ultimo_openverse
    with _vez_do_openverse:
        espera = _ultimo_openverse + ENTRE_PEDIDOS_S - time.monotonic()
        if espera > 0:
            time.sleep(espera)
        _ultimo_openverse = time.monotonic()


def _openverse(termo: str, orientacao: str, *, transporte=None) -> list[Achada]:
    import httpx

    _esperar_a_vez()
    params = {"q": termo, "license": ",".join(LICENCAS), "page_size": 20, "mature": "false",
              "size": "large"}
    # em pé, de todo formato: as fotos em pé com licença livre são poucas, e o quadro recorta o
    # meio de uma deitada
    if orientacao == "paisagem":
        params["aspect_ratio"] = "wide"
    try:
        with httpx.Client(transport=transporte, timeout=30.0,
                          headers={"User-Agent": AGENTE}) as cliente:
            r = cliente.get(OPENVERSE, params=params)
    except httpx.HTTPError as erro:
        raise SemFotos("Não consegui falar com o Openverse. Confira a internet.") from erro
    if r.status_code == 429:
        raise SemFotos("O Openverse pediu para esperar (muitas buscas seguidas). Tente de novo "
                       "em alguns minutos.")
    if r.status_code >= 400:
        raise SemFotos(f"O Openverse respondeu {r.status_code}.")
    achadas = []
    for d in r.json().get("results") or []:
        licenca = str(d.get("license") or "").lower()
        if licenca not in LICENCAS or not d.get("url"):
            continue
        etiquetas = " ".join(str(t.get("name", "")) for t in d.get("tags") or []
                             if isinstance(t, dict))
        if _nao_serve(str(d.get("title") or ""), etiquetas):
            continue
        largura, altura = int(d.get("width") or 0), int(d.get("height") or 0)
        if largura and altura and max(largura, altura) < LADO_MINIMO:
            continue
        fonte = str(d.get("source") or d.get("provider") or "").strip()
        achadas.append(Achada(
            url=str(d["url"]), titulo=str(d.get("title") or "")[:120],
            autor=str(d.get("creator") or "")[:80], licenca=licenca,
            versao=str(d.get("license_version") or ""),
            link=str(d.get("foreign_landing_url") or ""),
            licenca_url=str(d.get("license_url") or ""),
            fonte=f"Openverse ({fonte})" if fonte else "Openverse",
            largura=largura, altura=altura))
    return achadas


def _do_pexels(termo: str, orientacao: str, *, transporte=None) -> list[Achada]:
    if not (pexels._falso() or pexels.chave()):
        return []
    try:
        fotos = pexels.buscar(termo, orientacao, transporte=transporte)
    except pexels.ErroDoPexels as erro:
        logger.info("o Pexels não buscou: %s", erro)
        return []
    return [Achada(url=f.grande, titulo=f.alt, autor=f.autor, licenca="pexels", versao="",
                   link=f.pagina, licenca_url="https://www.pexels.com/license/", fonte="Pexels",
                   largura=f.largura, altura=f.altura, pexels_id=f.id)
            for f in fotos if not _nao_serve(f.alt)]


def procurar(termo: str, orientacao: str = "paisagem", *, transporte=None) -> list[Achada]:
    """As fotos para uma busca: as do Pexels (se houver a chave) primeiro, depois as do
    Openverse. Com o Pexels trazendo o bastante, o Openverse nem é consultado: cada busca nele
    levava uns 5 s (medido em 25/10/2026), e as fotos dele ficariam de reserva."""
    if falso():
        return [Achada(url=f"falso://{termo}/{k}", titulo=f"{termo} {k + 1}",
                       autor=f"Autora {k + 1}", licenca="by" if k % 2 else "cc0",
                       versao="4.0" if k % 2 else "", link=f"https://exemplo.org/{k}",
                       licenca_url="https://creativecommons.org/licenses/by/4.0/" if k % 2 else "",
                       fonte="Openverse (falso)", largura=1600, altura=900) for k in range(4)]
    achadas = _do_pexels(termo, orientacao, transporte=transporte)
    if len(achadas) >= POR_BLOCO * 2:
        return achadas
    try:
        achadas += _openverse(termo, orientacao, transporte=transporte)
    except SemFotos as erro:
        if not achadas:
            raise
        logger.info("o Openverse falhou, ficam as do Pexels: %s", erro)
    return achadas


def _procurar_ou_nada(termo: str, orientacao: str, *, transporte=None) -> list[Achada]:
    try:
        return procurar(termo, orientacao, transporte=transporte)
    except SemFotos as erro:
        logger.info("a busca %r não trouxe nada: %s", termo, erro)
        return []


def _procurar_todas(lista: Sequence[Busca], orientacao: str, *, transporte=None
                    ) -> list[tuple[list[Achada], SemFotos | None]]:
    """As buscas de todos os trechos, algumas ao mesmo tempo: cada uma leva meio segundo no
    Pexels, e uma depois da outra somavam 14 s num vídeo de 23 trechos (25/10/2026)."""
    def uma(busca: Busca) -> tuple[list[Achada], SemFotos | None]:
        try:
            return procurar(busca.termo, orientacao, transporte=transporte), None
        except SemFotos as erro:
            return [], erro

    with ThreadPoolExecutor(DE_UMA_VEZ) as grupo:
        return list(grupo.map(uma, lista))


# ── baixar e guardar ─────────────────────────────────────────────────────


def _gradiente(semente: str) -> bytes:
    from PIL import Image

    n = sum(ord(c) for c in semente)
    cor = ((n * 73) % 200 + 30, (n * 151) % 200 + 30, (n * 37) % 200 + 30)
    img = Image.linear_gradient("L").resize((1600, 900)).convert("RGB")
    img = Image.blend(img, Image.new("RGB", (1600, 900), cor), 0.6)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return buf.getvalue()


def _dados(a: Achada, *, previa: bool = False, transporte=None) -> bytes | None:
    """Os bytes da foto (ou da prévia, que só o Pexels tem). ``None`` quando não deu."""
    import httpx

    if falso() or a.url.startswith("falso://"):
        return _gradiente(a.url)
    if a.pexels_id is not None:
        try:
            return pexels.baixar(a.pexels_id, "previa" if previa else "grande",
                                 transporte=transporte)
        except pexels.ErroDoPexels:
            return None
    try:
        with httpx.Client(transport=transporte, timeout=45.0, follow_redirects=True,
                          headers={"User-Agent": AGENTE}) as cliente:
            r = cliente.get(a.url)
    except httpx.HTTPError:
        return None
    return r.content if r.status_code < 400 else None


def _guardar(dados: bytes | None, destino: Path) -> bool:
    from PIL import Image, ImageOps

    if not dados:
        return False
    try:
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(dados))).convert("RGB")
    except Exception:
        return False
    if max(img.size) < LADO_MINIMO * 0.8:
        return False
    img.thumbnail((LADO_GUARDADO, LADO_GUARDADO), Image.LANCZOS)
    destino.parent.mkdir(parents=True, exist_ok=True)
    img.save(destino, "JPEG", quality=88)
    return True


def baixar(a: Achada, destino: Path, *, transporte=None) -> bool:
    """A foto em ``destino`` (JPEG, no máximo ``LADO_GUARDADO`` de lado). ``False`` quando não
    deu (fora do ar, não é imagem, pequena demais)."""
    return _guardar(_dados(a, transporte=transporte), destino)


# ── o auditor ────────────────────────────────────────────────────────────


@dataclass
class _Prova:
    """Uma candidata pronta para a nota."""

    achada: Achada
    imagem: object              # a PIL.Image da prévia (ou da foto inteira)
    #: A foto inteira, quando foi ela que veio: fica para guardar, sem baixar de novo.
    inteira: bytes | None


def _provas(candidatas: Sequence[Achada], *, transporte=None) -> list[_Prova]:
    """As imagens que o auditor confere, baixadas ao mesmo tempo: a prévia do Pexels, ou a foto
    inteira das outras fontes. As que não vieram ficam de fora."""
    from PIL import Image

    pela_previa = [a for a in candidatas if a.pexels_id is not None][:CONFERIDAS]
    inteiras = [a for a in candidatas if a.pexels_id is None][:CONFERIDAS_INTEIRAS]
    lista = [a for a in candidatas if a in pela_previa or a in inteiras][:CONFERIDAS]

    def uma(a: Achada) -> _Prova | None:
        previa = a.pexels_id is not None
        dados = _dados(a, previa=previa, transporte=transporte)
        if not dados:
            return None
        try:
            img = Image.open(io.BytesIO(dados))
            img.draft("RGB", (auditor.LADO * 2, auditor.LADO * 2))   # o JPEG grande abre menor
            img = img.convert("RGB")
        except Exception:
            return None
        return _Prova(a, img, None if previa else dados)

    with ThreadPoolExecutor(DE_UMA_VEZ) as grupo:
        return [p for p in grupo.map(uma, lista) if p is not None]


def _pela_nota(busca: Busca, candidatas: list[Achada], ja: list, achado: Achado, *,
               orientacao: str, usadas: set[str], transporte=None
               ) -> tuple[list[tuple], tuple | None]:
    """As candidatas que mostram o trecho, da que mais combina à que menos, como (a foto, os
    bytes dela se já vieram, o vetor). Com menos de ``POR_BLOCO`` passando do piso, vem a
    busca de reserva. Nenhuma passando, vai à parte a melhor de todas: é a do trecho se o
    vídeo inteiro ficar sem foto nenhuma."""
    provas = _provas(candidatas, transporte=transporte)
    notas = auditor.avaliar([p.imagem for p in provas], busca.alvo)
    ordem = auditor.escolher(notas, len(provas), ja=ja)
    if len(ordem) < POR_BLOCO and busca.reserva:
        vistas = {a.url for a in candidatas} | usadas
        mais = [a for a in _procurar_ou_nada(busca.reserva, orientacao, transporte=transporte)
                if a.url not in vistas]
        extra = _provas(mais, transporte=transporte)
        notas = auditor.juntar(notas, auditor.avaliar([p.imagem for p in extra], busca.alvo))
        provas += extra
        ordem = auditor.escolher(notas, len(provas), ja=ja)
    achado.olhadas += len(provas)
    achado.recusadas += sum(n < auditor.PISO for n in notas.notas)
    melhor = None
    if not ordem and provas:
        i = max(range(len(provas)), key=lambda i: notas.notas[i])
        melhor = (provas[i].achada, provas[i].inteira)
    return [(provas[i].achada, provas[i].inteira, notas.vetores[i]) for i in ordem], melhor


def _por(achado: Achado, k: int, busca: Busca, a: Achada, inteira: bytes | None, *,
         transporte=None) -> bool:
    """Guarda a foto na pasta e a anota na matriz e nos créditos."""
    n = len(achado.cenas) + 1
    nome = f"foto-{n:03d}.jpg"
    if not _guardar(inteira or _dados(a, transporte=transporte), achado.pasta / nome):
        return False
    achado.cenas.append({
        "id": f"foto-{n:03d}", "arquivo": nome, "descricao": busca.descricao,
        "categorias": [], "personagens": [], "periodo": "n/a", "energia": "media",
        "monetizacao": "ok", "obs": f"para o trecho {k + 1}: {busca.bloco[:90]}",
        "trecho": k + 1})
    achado.creditos.append(f"{nome}: {a.credito()}")
    return True


def achar(roteiro: str, pasta: Path, *, tema: str = "", orientacao: str = "paisagem",
          conferir: bool = True, progresso: Progresso | None = None,
          parar: Callable[[], bool] = lambda: False, transporte=None) -> Achado:
    """As fotos do roteiro, na ``pasta``, com o ``cenas.json`` e o ``creditos.txt``. Com
    ``conferir``, o auditor escolhe entre as candidatas de cada busca (ele é baixado na
    primeira vez)."""
    trechos = blocos(roteiro)
    if not trechos:
        raise SemFotos("O roteiro está vazio: escreva (ou gere) o roteiro antes de achar as fotos.")
    if progresso:
        progresso("buscando", 0, len(trechos))
    lista, pedidos = buscas(trechos, tema, transporte=transporte)
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    achado = Achado(pasta, pedidos=pedidos)
    achadas = _procurar_todas(lista, orientacao, transporte=transporte)
    if conferir:
        if progresso and not auditor.baixado():
            progresso("auditor", 0, len(trechos))
        achado.conferidas = auditor.preparar([b.alvo for b in lista])
        if not achado.conferidas:
            achado.aviso = ("O auditor das fotos não carregou (na primeira vez ele é baixado: "
                            "confira a internet). Ficaram as primeiras fotos de cada busca.")
    etapa = "conferindo" if achado.conferidas else "baixando"
    usadas: set[str] = set()
    ja: list = []                   # os vetores das fotos postas: nenhuma cena se repete
    melhores: list[tuple] = []      # a melhor de cada trecho em que nenhuma passou do piso
    try:
        for k, busca in enumerate(lista):
            if parar():
                break
            if progresso:
                progresso(etapa, k, len(trechos))
            candidatas, erro = achadas[k]
            if erro is not None:
                if not achado.cenas and not melhores and k == len(lista) - 1:
                    raise erro
                logger.info("o trecho %d ficou sem busca: %s", k, erro)
            candidatas = [a for a in candidatas if a.url not in usadas]
            if achado.conferidas:
                fila, melhor = _pela_nota(busca, candidatas, ja, achado, orientacao=orientacao,
                                          usadas=usadas, transporte=transporte)
                if melhor:
                    melhores.append((k, busca, *melhor))
            else:
                fila = [(a, None, None) for a in candidatas]
            postas = 0
            for a, inteira, vetor in fila:
                if postas >= POR_BLOCO:
                    break
                usadas.add(a.url)
                if _por(achado, k, busca, a, inteira, transporte=transporte):
                    postas += 1
                    if vetor is not None:
                        ja.append(vetor)
            if not postas:
                achado.sem_foto.append(k)
        if not achado.cenas and melhores:
            # o auditor recusou tudo: a foto que mais se aproxima é melhor que vídeo nenhum (e
            # a mesma pode ter sido a melhor de dois trechos)
            for k, busca, a, inteira in melhores:
                if a.url not in usadas and _por(achado, k, busca, a, inteira,
                                                transporte=transporte):
                    achado.sem_foto.remove(k)
                usadas.add(a.url)
            achado.aviso = ("Nenhuma foto achada mostrava bem o roteiro: ficaram as que mais se "
                            "aproximam. Tente outras palavras, ou mande as suas cenas.")
    finally:
        if achado.conferidas:
            auditor.soltar()
    if progresso:
        progresso(etapa, len(trechos), len(trechos))
    if not achado.cenas:
        raise SemFotos("Não achei nenhuma foto para este roteiro. Tente outras palavras, ou "
                       "marque as cenas e mande as suas.")
    (pasta / "cenas.json").write_text(json.dumps(achado.cenas, ensure_ascii=False, indent=2)
                                      + "\n", encoding="utf-8")
    cabeca = ("As fotos deste vídeo e as licenças delas. As CC BY pedem o crédito: cole estas "
              "linhas na descrição do vídeo.\n\n")
    (pasta / "creditos.txt").write_text(cabeca + "\n".join(achado.creditos) + "\n",
                                        encoding="utf-8")
    return achado


# ── as fotos no vídeo ────────────────────────────────────────────────────


def _nua(palavra: str) -> str:
    return _sem_acento(palavra).strip(".,;:!?\"'()…—–-“”")


def _no_roteiro(fala: Sequence[str], roteiro: Sequence[str]) -> tuple[list[int], int]:
    """A posição de cada palavra da fala no roteiro, pelo alinhamento das duas (a fala pode
    ter perdido frases no "Quanto tempo?", e o Whisper, trocado uma palavra), e quantas
    casaram. A que não casa fica com a posição da anterior."""
    a, b = [_nua(w) for w in fala], [_nua(w) for w in roteiro]
    posicao: list[int | None] = [None] * len(a)
    casadas = 0
    for i, j, n in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks():
        casadas += n
        for d in range(n):
            posicao[i + d] = j + d
    saida, ultima = [], 0
    for p in posicao:
        ultima = p if p is not None else ultima
        saida.append(ultima)
    return saida, casadas


def pelos_trechos(blocos_da_fala: Sequence, biblioteca, palavras: Sequence,
                  roteiro: str) -> list[list[str]] | None:
    """As fotos achadas no vídeo: cada bloco da fala toca as fotos do trecho do roteiro em
    que ele está, na ordem, sem pedir à IA. Com 46 fotos para 25 blocos e a regra de não
    repetir cena, ela punha a foto do trecho 1 no trecho 18 (o vídeo do GPS, 26/10/2026). O
    trecho sem foto fica com as do anterior. ``None`` quando a biblioteca não é de fotos
    achadas, ou a fala não é a do roteiro (menos da metade das palavras casa)."""
    from editor.cenas import cenas_por_bloco

    por_trecho: dict[int, list[str]] = {}
    for c in biblioteca.cenas:
        if c.trecho <= 0:
            return None
        por_trecho.setdefault(c.trecho - 1, []).append(c.id)
    trechos = blocos(roteiro)
    if not por_trecho or not trechos or not palavras:
        return None
    comecos, n = [], 0
    for t in trechos:
        comecos.append(n)
        n += len(t.split())
    no_roteiro, casadas = _no_roteiro([w.texto for w in palavras], roteiro.split())
    if casadas * 2 < len(palavras):
        return None
    vez: dict[int, int] = {}
    escolhas: list[list[str]] = []
    for b in blocos_da_fala:
        if b.ultima < b.primeira:                   # um bloco sem fala segue o anterior
            escolhas.append(escolhas[-1] if escolhas else por_trecho[min(por_trecho)][:1])
            continue
        meio = sorted(no_roteiro[b.primeira:b.ultima + 1])[(b.ultima - b.primeira) // 2]
        k = bisect.bisect_right(comecos, meio) - 1
        k = max([t for t in por_trecho if t <= k] or [min(por_trecho)])
        ids, comeco = por_trecho[k], vez.get(k, 0)
        quantas = min(len(ids), cenas_por_bloco(b))
        escolhas.append([ids[(comeco + i) % len(ids)] for i in range(quantas)])
        vez[k] = comeco + quantas
    return escolhas


__all__ = ["LICENCAS", "Achada", "Achado", "Busca", "SemFotos", "achar", "baixar", "blocos",
           "buscas", "esquema", "falso", "montar_pedido", "pelos_trechos", "procurar",
           "termo_pelas_palavras"]
