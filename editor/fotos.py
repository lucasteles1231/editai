"""
As fotos achadas pelo que é dito (o vídeo só pelo tema). Sem vídeo e sem cenas, o roteiro vira
uma biblioteca de cenas de fotos, com a licença de cada uma conferida e os créditos ao lado.

1. **Os blocos:** o roteiro é partido nos trechos em que a imagem muda (os parágrafos dele, e
   os longos nas frases).
2. **As buscas:** a IA escreve, num pedido só, a busca de cada bloco em inglês (o que mostrar,
   concreto) e uma descrição curta em português (que o roteiro do vídeo lê para escolher a foto
   de cada trecho). Sem a IA, a busca é o próprio bloco, sem as palavras vazias.
3. **As fontes:**
   - **o Pexels**, com a chave de quem usa (fotos de uso livre);
   - **o Openverse**, sem chave, só com as licenças que deixam pôr a foto num vídeo sem pedir:
     CC0, domínio público e CC BY (que pede o crédito). A BY-SA (que obrigaria o vídeo à mesma
     licença), a NC e a ND ficam de fora.
4. **A triagem pelo texto:** saem a foto pequena (menos de ``LADO_MINIMO`` no lado maior), a
   que é texto, logo, diagrama ou captura de tela pelo título e pelas etiquetas, e a repetida.
5. **A pasta:** ``Filmes/editor-de-video/fotos/<tema>``, com as fotos, o ``cenas.json`` (a
   descrição de cada uma) e o ``creditos.txt``, para colar na descrição do vídeo.
6. **O bloco sem foto** fica sem: as fotos dos vizinhos cobrem o trecho.

Para os testes há as fotos falsas (``EDITOR_FOTOS=falso``): gradientes desenhados aqui, sem
rede, e uma IA falsa que devolve a busca pelo próprio bloco.
"""
from __future__ import annotations

import io
import json
import logging
import os
import re
import time
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from editor import ia, pexels

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
#: O intervalo entre dois pedidos ao Openverse (o anônimo tem limite por minuto).
ENTRE_PEDIDOS_S = 0.4
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
        "k": {"type": "integer"}, "busca": {"type": "string"},
        "descricao": {"type": "string"}}, "required": ["k", "busca", "descricao"]}
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
        descricao = re.sub(r"\s+", " ", str(item.get("descricao") or "")).strip()[:140]
        if termo:
            saida[k] = Busca(blocos_[k], termo, descricao or saida[k].descricao)
    return saida, len(gasto)


# ── as fontes ────────────────────────────────────────────────────────────


def _nao_serve(*textos: str) -> bool:
    # palavra inteira: "text" não pode derrubar "texture", nem "icon", "iconic"
    junto = _sem_acento(" ".join(textos))
    return any(re.search(rf"(?<!\w){re.escape(_sem_acento(p))}(?!\w)", junto) for p in NAO_SERVE)


def _openverse(termo: str, orientacao: str, *, transporte=None) -> list[Achada]:
    import httpx

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


def baixar(a: Achada, destino: Path, *, transporte=None) -> bool:
    """A foto em ``destino`` (JPEG, no máximo ``LADO_GUARDADO`` de lado). ``False`` quando não
    deu (fora do ar, não é imagem, pequena demais)."""
    import httpx
    from PIL import Image, ImageOps

    if falso() or a.url.startswith("falso://"):
        dados = _gradiente(a.url)
    elif a.pexels_id is not None:
        try:
            dados = pexels.baixar(a.pexels_id, "grande", transporte=transporte)
        except pexels.ErroDoPexels:
            return False
    else:
        try:
            with httpx.Client(transport=transporte, timeout=45.0, follow_redirects=True,
                              headers={"User-Agent": AGENTE}) as cliente:
                r = cliente.get(a.url)
        except httpx.HTTPError:
            return False
        if r.status_code >= 400:
            return False
        dados = r.content
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


def achar(roteiro: str, pasta: Path, *, tema: str = "", orientacao: str = "paisagem",
          progresso: Progresso | None = None, parar: Callable[[], bool] = lambda: False,
          transporte=None) -> Achado:
    """As fotos do roteiro, na ``pasta``, com o ``cenas.json`` e o ``creditos.txt``."""
    trechos = blocos(roteiro)
    if not trechos:
        raise SemFotos("O roteiro está vazio: escreva (ou gere) o roteiro antes de achar as fotos.")
    if progresso:
        progresso("buscando", 0, len(trechos))
    lista, pedidos = buscas(trechos, tema, transporte=transporte)
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    achado = Achado(pasta, pedidos=pedidos)
    usadas: set[str] = set()
    for k, busca in enumerate(lista):
        if parar():
            break
        if progresso:
            progresso("baixando", k, len(trechos))
        try:
            candidatas = procurar(busca.termo, orientacao, transporte=transporte)
        except SemFotos as erro:
            if not achado.cenas and k == len(lista) - 1:
                raise
            logger.info("o trecho %d ficou sem busca: %s", k, erro)
            candidatas = []
        postas = 0
        for a in candidatas:
            if postas >= POR_BLOCO:
                break
            if a.url in usadas:
                continue
            usadas.add(a.url)
            n = len(achado.cenas) + 1
            nome = f"foto-{n:03d}.jpg"
            if not baixar(a, pasta / nome, transporte=transporte):
                continue
            achado.cenas.append({
                "id": f"foto-{n:03d}", "arquivo": nome, "descricao": busca.descricao,
                "categorias": [], "personagens": [], "periodo": "n/a", "energia": "media",
                "monetizacao": "ok", "obs": f"para o trecho {k + 1}: {busca.bloco[:90]}"})
            achado.creditos.append(f"{nome}: {a.credito()}")
            postas += 1
        if not postas:
            achado.sem_foto.append(k)
        if not falso():
            time.sleep(ENTRE_PEDIDOS_S)
    if progresso:
        progresso("baixando", len(trechos), len(trechos))
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


__all__ = ["LICENCAS", "Achada", "Achado", "Busca", "SemFotos", "achar", "baixar", "blocos",
           "buscas", "esquema", "falso", "montar_pedido", "procurar", "termo_pelas_palavras"]
