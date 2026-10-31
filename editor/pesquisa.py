"""
A pesquisa na internet, como ferramenta da IA: só fontes grátis e sem chave. A IA (a local
ou a de uma chave) pede, o Editai busca, e o que volta vai numerado, para o roteiro dizer de
onde veio cada fato.

**As ferramentas:**

- ``pesquisar(consulta, tipo)``: ``"fatos"`` busca na Wikipédia (grátis, pede só um
  ``User-Agent`` que diga quem é); ``"noticias"``, as manchetes dos últimos dias;
- ``ler(link)``: o texto de uma página dos resultados, cortado em ``LER_MAXIMO`` letras.

**As fontes de notícias** (medidas em 26/10/2026):

- **o Bing Notícias (RSS):** responde em menos de 1 s, e o link leva à matéria. Não há termos
  de uso publicados para o RSS: a API de busca do Bing foi encerrada em 2025;
- **o Google Notícias (RSS):** responde em 1 s, com o título, o veículo e a data, mas o link
  só chega à matéria rodando JavaScript. Também sem termos publicados para o RSS;
- **o GDELT:** os termos liberam qualquer uso, com a citação, mas o anônimo recebeu 429 em
  todos os pedidos daquele dia, mesmo com 45 s entre eles.

Cada sessão (:class:`Pesquisa`) tem um teto de buscas e de leituras: é a IA quem decide
buscar, e um modelo pequeno pode pedir a mesma coisa em volta.

Para os testes há a pesquisa falsa (``EDITOR_PESQUISA=falsa``): resultados fixos, sem rede.
"""
from __future__ import annotations

import html
import json
import logging
import os
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from urllib.parse import parse_qs, quote, urlparse

from editor import __version__

logger = logging.getLogger(__name__)

AGENTE = f"Editai/{__version__} (https://github.com/lucasteles1231/editai) httpx"
WIKIPEDIA = "https://{idioma}.wikipedia.org/w/api.php"
BING = "https://www.bing.com/news/search"
GOOGLE = "https://news.google.com/rss/search"
GDELT = "https://api.gdeltproject.org/api/v2/doc/doc"
#: As fontes de notícias, na ordem em que são tentadas.
FONTES_DE_NOTICIAS = ("bing", "google")
#: O tamanho máximo do texto de uma página lida, e de um trecho de resultado.
LER_MAXIMO = 4000
TRECHO_MAXIMO = 300
#: Um parágrafo com menos letras que isto é menu, rodapé ou legenda de foto.
PARAGRAFO_MINIMO = 60
TEMPO_LIMITE_S = 20.0
VARIAVEL_FALSA = "EDITOR_PESQUISA"

#: As ferramentas no formato das APIs compatíveis com a da OpenAI (o llama-server também).
FERRAMENTAS = [
    {"type": "function", "function": {
        "name": "pesquisar",
        "description": ("Busca na internet. tipo \"fatos\": a Wikipédia (o que é, quem é, "
                        "datas, números conhecidos). tipo \"noticias\": as manchetes dos "
                        "últimos dias. Use quando o assunto pede informação atual ou um fato "
                        "de que você não tem certeza."),
        "parameters": {"type": "object", "properties": {
            "consulta": {"type": "string", "description": "poucas palavras, como numa busca"},
            "tipo": {"type": "string", "enum": ["fatos", "noticias"]}},
            "required": ["consulta", "tipo"]}}},
    {"type": "function", "function": {
        "name": "ler",
        "description": "O texto de uma página dos resultados, pelo link dela.",
        "parameters": {"type": "object", "properties": {
            "link": {"type": "string"}}, "required": ["link"]}}},
]


class SemPesquisa(RuntimeError):
    """A fonte não respondeu (a mensagem diz qual e por quê)."""


@dataclass
class Resultado:
    titulo: str
    trecho: str
    link: str
    fonte: str          # "Wikipédia", "CNN Brasil"…
    data: str = ""      # AAAA-MM-DD, quando se sabe
    numero: int = 0     # o número com que a IA cita


def falsa() -> bool:
    return os.environ.get(VARIAVEL_FALSA, "").strip().lower() == "falsa"


def _falsos(consulta: str, fonte: str) -> list[Resultado]:
    return [Resultado(f"{consulta}: o que se sabe ({k + 1})", f"Um trecho sobre {consulta}.",
                      f"https://exemplo.org/{fonte.lower()}/{k + 1}", fonte, "2026-10-25")
            for k in range(2)]


def _limpo(texto: str, maximo: int = TRECHO_MAXIMO) -> str:
    texto = html.unescape(re.sub(r"<[^>]+>", " ", texto or ""))
    return re.sub(r"\s+", " ", texto).strip()[:maximo]


def _cliente(transporte=None):
    import httpx

    return httpx.Client(transport=transporte, timeout=TEMPO_LIMITE_S, follow_redirects=True,
                        headers={"User-Agent": AGENTE})


def _pedir(url: str, params: dict | None = None, *, transporte=None):
    import httpx

    try:
        with _cliente(transporte) as cliente:
            r = cliente.get(url, params=params)
    except httpx.HTTPError as erro:
        raise SemPesquisa(f"{urlparse(url).netloc} não respondeu: {erro}") from erro
    if r.status_code >= 400:
        raise SemPesquisa(f"{urlparse(url).netloc} respondeu {r.status_code}")
    return r


def _data_rss(texto: str) -> str:
    from email.utils import parsedate_to_datetime

    try:
        return parsedate_to_datetime(texto).date().isoformat()
    except (TypeError, ValueError):
        return ""


# ── as fontes ────────────────────────────────────────────────────────────


def fatos(consulta: str, *, idioma: str = "pt", quantos: int = 3,
          transporte=None) -> list[Resultado]:
    """Os artigos da Wikipédia para a consulta, com o trecho que casou e a data da última
    edição (a página de um assunto do momento é editada no mesmo dia)."""
    if falsa():
        return _falsos(consulta, "Wikipédia")
    r = _pedir(WIKIPEDIA.format(idioma=idioma), {
        "action": "query", "list": "search", "srsearch": consulta, "srlimit": quantos,
        "srprop": "snippet|timestamp", "format": "json", "utf8": 1}, transporte=transporte)
    return [Resultado(a["title"], _limpo(a.get("snippet", "")),
                      f"https://{idioma}.wikipedia.org/wiki/{quote(a['title'].replace(' ', '_'))}",
                      "Wikipédia", str(a.get("timestamp", ""))[:10])
            for a in r.json().get("query", {}).get("search", [])]


def _bing(consulta: str, quantos: int, transporte=None) -> list[Resultado]:
    r = _pedir(BING, {"q": consulta, "format": "rss", "setlang": "pt-BR", "cc": "BR"},
               transporte=transporte)
    saida = []
    for it in ET.fromstring(r.content).findall(".//item")[:quantos]:
        link = it.findtext("link") or ""
        # o link do RSS passa pelo Bing; o da matéria vai no "url"
        direto = parse_qs(urlparse(link).query).get("url", [link])[0]
        fonte = (it.findtext("{https://www.bing.com:443/news/search?q=}Source")
                 or urlparse(direto).netloc.removeprefix("www."))
        saida.append(Resultado(_limpo(it.findtext("title") or ""),
                               _limpo(it.findtext("description") or ""), direto, fonte,
                               _data_rss(it.findtext("pubDate") or "")))
    return saida


def _google(consulta: str, quantos: int, dias: int, transporte=None) -> list[Resultado]:
    r = _pedir(GOOGLE, {"q": f"{consulta} when:{dias}d", "hl": "pt-BR", "gl": "BR",
                        "ceid": "BR:pt-419"}, transporte=transporte)
    saida = []
    for it in ET.fromstring(r.content).findall(".//item")[:quantos]:
        fonte = it.find("source")
        titulo = _limpo(it.findtext("title") or "")
        nome = fonte.text if fonte is not None and fonte.text else ""
        # o título vem com " - Veículo" no fim
        titulo = titulo.removesuffix(f" - {nome}") if nome else titulo
        saida.append(Resultado(titulo, "", it.findtext("link") or "", nome,
                               _data_rss(it.findtext("pubDate") or "")))
    return saida


def noticias(consulta: str, *, quantos: int = 8, dias: int = 7,
             fontes: tuple[str, ...] = FONTES_DE_NOTICIAS, transporte=None) -> list[Resultado]:
    """As manchetes dos últimos ``dias`` sobre a consulta, da primeira fonte que responder."""
    if falsa():
        return _falsos(consulta, "Jornal")
    erros = []
    for nome in fontes:
        try:
            achadas = (_bing(consulta, quantos, transporte) if nome == "bing"
                       else _google(consulta, quantos, dias, transporte))
        except (SemPesquisa, ET.ParseError) as erro:
            erros.append(f"{nome}: {erro}")
            continue
        if achadas:
            return achadas
    if erros:
        raise SemPesquisa("; ".join(erros))
    return []


class _Paragrafos:
    """Os parágrafos de uma página: o texto de cada ``<p>``, sem os curtos (menus)."""

    @staticmethod
    def de(pagina: str) -> list[str]:
        pagina = re.sub(r"(?is)<(script|style|nav|header|footer|aside)\b.*?</\1>", " ", pagina)
        trechos = [_limpo(p, 10_000) for p in re.findall(r"(?is)<p\b[^>]*>(.*?)</p>", pagina)]
        return [t for t in trechos if len(t) >= PARAGRAFO_MINIMO]


def ler(link: str, *, transporte=None) -> str:
    """O texto da página, cortado em ``LER_MAXIMO``. Na Wikipédia, o texto do artigo pela
    API; nas outras, os parágrafos do HTML."""
    if falsa():
        return f"O texto da página {link}, falso, dos testes."
    url = urlparse(link)
    if url.scheme not in ("http", "https"):
        raise SemPesquisa("o link precisa começar com http ou https")
    if url.netloc.endswith("wikipedia.org") and url.path.startswith("/wiki/"):
        titulo = url.path.removeprefix("/wiki/")
        r = _pedir(f"https://{url.netloc}/w/api.php", {
            "action": "query", "prop": "extracts", "explaintext": 1, "format": "json",
            "titles": titulo.replace("_", " "), "redirects": 1}, transporte=transporte)
        pagina = next(iter(r.json().get("query", {}).get("pages", {}).values()), {})
        return re.sub(r"\n{3,}", "\n\n", pagina.get("extract", ""))[:LER_MAXIMO]
    r = _pedir(link, transporte=transporte)
    if "html" not in r.headers.get("content-type", ""):
        raise SemPesquisa("a página não é um texto que dá para ler")
    texto = "\n\n".join(_Paragrafos.de(r.text))
    if not texto:
        raise SemPesquisa("a página não tem texto que dê para ler sem o navegador")
    return texto[:LER_MAXIMO]


# ── a sessão ─────────────────────────────────────────────────────────────


@dataclass
class Pesquisa:
    """As buscas de uma tarefa: o teto, o registro do que foi feito e as fontes numeradas."""

    buscas_max: int = 4
    leituras_max: int = 3
    fontes: list[Resultado] = field(default_factory=list)
    feitas: list[dict] = field(default_factory=list)
    transporte: object = None

    def _numerar(self, achadas: list[Resultado]) -> list[Resultado]:
        saida = []
        for a in achadas:
            ja = next((f for f in self.fontes if f.link == a.link), None)
            if ja is None:
                a.numero = len(self.fontes) + 1
                self.fontes.append(a)
                ja = a
            saida.append(ja)
        return saida

    def pesquisar(self, consulta: str, tipo: str) -> list[Resultado]:
        consulta = re.sub(r"\s+", " ", str(consulta or "")).strip()[:120]
        if not consulta:
            raise SemPesquisa("a consulta veio vazia")
        if sum(f["ferramenta"] == "pesquisar" for f in self.feitas) >= self.buscas_max:
            raise SemPesquisa(f"o limite de {self.buscas_max} buscas desta tarefa acabou")
        comeco = time.monotonic()
        registro = {"ferramenta": "pesquisar", "consulta": consulta, "tipo": tipo}
        try:
            achadas = (noticias(consulta, transporte=self.transporte) if tipo == "noticias"
                       else fatos(consulta, transporte=self.transporte))
        except SemPesquisa as erro:
            self.feitas.append({**registro, "erro": str(erro),
                                "segundos": round(time.monotonic() - comeco, 1)})
            raise
        self.feitas.append({**registro, "resultados": len(achadas),
                            "segundos": round(time.monotonic() - comeco, 1)})
        return self._numerar(achadas)

    def ler(self, link: str) -> str:
        if sum(f["ferramenta"] == "ler" for f in self.feitas) >= self.leituras_max:
            raise SemPesquisa(f"o limite de {self.leituras_max} leituras desta tarefa acabou")
        comeco = time.monotonic()
        try:
            texto = ler(str(link or ""), transporte=self.transporte)
        except SemPesquisa as erro:
            self.feitas.append({"ferramenta": "ler", "link": link, "erro": str(erro),
                                "segundos": round(time.monotonic() - comeco, 1)})
            raise
        self.feitas.append({"ferramenta": "ler", "link": link, "letras": len(texto),
                            "segundos": round(time.monotonic() - comeco, 1)})
        return texto

    def executar(self, nome: str, argumentos: dict) -> str:
        """Roda a ferramenta que a IA pediu e devolve o texto da resposta para ela (os
        erros também vão como texto: a IA segue sem aquela fonte)."""
        try:
            if nome == "pesquisar":
                achadas = self.pesquisar(argumentos.get("consulta", ""),
                                         argumentos.get("tipo", "fatos"))
                return json.dumps([{"n": a.numero, "titulo": a.titulo, "trecho": a.trecho,
                                    "fonte": a.fonte, "data": a.data, "link": a.link}
                                   for a in achadas], ensure_ascii=False)
            if nome == "ler":
                return self.ler(argumentos.get("link", ""))
            return json.dumps({"erro": f"não existe a ferramenta {nome}"}, ensure_ascii=False)
        except SemPesquisa as erro:
            return json.dumps({"erro": str(erro)}, ensure_ascii=False)

    def para_o_pedido(self) -> str:
        """As fontes numeradas, para o pedido final."""
        return "\n".join(f"[{f.numero}] {f.fonte}, {f.data or 's/d'}: {f.titulo}. {f.trecho}"
                         for f in self.fontes)

    def para_json(self) -> dict:
        return {"feitas": self.feitas, "fontes": [asdict(f) for f in self.fontes]}


__all__ = ["FERRAMENTAS", "Pesquisa", "Resultado", "SemPesquisa", "falsa", "fatos", "ler",
           "noticias"]
