"""
A pesquisa na internet (editor/pesquisa.py) e a IA que pesquisa (ia.pesquisar_notas): as
fontes grátis com a rede imitada (a Wikipédia, o RSS do Bing e o do Google, e a página de uma
notícia), o teto de buscas e de leituras, a conversa com as ferramentas na IA local e no Gemini
e o roteiro pelo tema com as fontes.
"""
from __future__ import annotations

import json

import httpx
import pytest

from editor import escrita, ia, pesquisa

BING = """<?xml version="1.0"?><rss><channel>
<item><title>GTA 6 vende 6 milhões na pré-venda</title>
<link>http://www.bing.com/news/apiclick.aspx?ref=FexRss&amp;url=https%3a%2f%2fjornal.exemplo%2fgta</link>
<description>A pré-venda passou de 6 milhões.</description>
<pubDate>Wed, 21 Oct 2026 10:00:00 GMT</pubDate></item>
</channel></rss>"""

GOOGLE = """<?xml version="1.0"?><rss><channel>
<item><title>GTA 6 chega em novembro - Revista</title>
<link>https://news.google.com/rss/articles/abc</link>
<pubDate>Thu, 22 Oct 2026 12:00:00 GMT</pubDate><source url="https://revista.exemplo">Revista</source></item>
</channel></rss>"""

MATERIA = """<html><head><script>var x = "<p>não é texto</p>";</script></head><body>
<nav><p>Início · Jogos · Política · Esportes · Mais notícias de hoje aqui no menu</p></nav>
<p>Curto demais.</p>
<p>A Rockstar confirmou que GTA 6 chega em 19 de novembro, e a pré-venda passou de
seis milhões de cópias.</p>
<p>O preço no Brasil é de R$ 450 na edição padrão e de R$ 550 na Ultimate, segundo a
loja oficial.</p>
</body></html>"""


class _Rede:
    def __init__(self, bing: int = 200):
        self.bing = bing
        self.pedidos: list[str] = []

    def __call__(self, pedido: httpx.Request) -> httpx.Response:
        url = pedido.url
        self.pedidos.append(url.host)
        if url.host.endswith("wikipedia.org"):
            if url.params.get("list") == "search":
                return httpx.Response(200, json={"query": {"search": [
                    {"title": "Grand Theft Auto VI", "timestamp": "2026-10-25T13:36:28Z",
                     "snippet": "Grand Theft Auto VI é um <span>jogo</span> eletrônico"}]}})
            return httpx.Response(200, json={"query": {"pages": {"1": {
                "extract": "Grand Theft Auto VI é um jogo.\n\n\n\nLançamento: 2026."}}}})
        if url.host == "www.bing.com":
            return httpx.Response(self.bing, content=BING.encode())
        if url.host == "news.google.com":
            return httpx.Response(200, content=GOOGLE.encode())
        if url.host == "jornal.exemplo":
            return httpx.Response(200, content=MATERIA.encode(),
                                  headers={"content-type": "text/html; charset=utf-8"})
        return httpx.Response(404)

    @property
    def transporte(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)


@pytest.fixture
def de_verdade(monkeypatch):
    monkeypatch.delenv(pesquisa.VARIAVEL_FALSA, raising=False)


def test_os_fatos_da_wikipedia(de_verdade):
    r = pesquisa.fatos("GTA 6", transporte=_Rede().transporte)
    assert r[0].titulo == "Grand Theft Auto VI" and r[0].fonte == "Wikipédia"
    assert r[0].trecho == "Grand Theft Auto VI é um jogo eletrônico" and r[0].data == "2026-10-25"
    assert r[0].link == "https://pt.wikipedia.org/wiki/Grand_Theft_Auto_VI"


def test_as_noticias_do_bing_com_o_link_da_materia(de_verdade):
    rede = _Rede()
    r = pesquisa.noticias("GTA 6", transporte=rede.transporte)
    assert r[0].link == "https://jornal.exemplo/gta"           # sem passar pelo Bing
    assert r[0].fonte == "jornal.exemplo" and r[0].data == "2026-10-21"
    assert r[0].trecho == "A pré-venda passou de 6 milhões." and rede.pedidos == ["www.bing.com"]


def test_sem_o_bing_vem_o_google(de_verdade):
    rede = _Rede(bing=503)
    r = pesquisa.noticias("GTA 6", transporte=rede.transporte)
    assert r[0].titulo == "GTA 6 chega em novembro" and r[0].fonte == "Revista"
    assert rede.pedidos == ["www.bing.com", "news.google.com"]


def test_ler_a_materia_e_o_artigo(de_verdade):
    rede = _Rede()
    texto = pesquisa.ler("https://jornal.exemplo/gta", transporte=rede.transporte)
    assert texto.startswith("A Rockstar confirmou") and "R$ 450" in texto
    assert "Curto demais" not in texto and "menu" not in texto and "não é texto" not in texto
    artigo = pesquisa.ler("https://pt.wikipedia.org/wiki/Grand_Theft_Auto_VI",
                          transporte=rede.transporte)
    assert artigo == "Grand Theft Auto VI é um jogo.\n\nLançamento: 2026."
    with pytest.raises(pesquisa.SemPesquisa, match="http"):
        pesquisa.ler("file:///etc/passwd")


def test_a_sessao_numera_conta_e_tem_teto(de_verdade):
    p = pesquisa.Pesquisa(buscas_max=2, leituras_max=1, transporte=_Rede().transporte)
    primeiras = p.pesquisar("GTA 6", "noticias")
    de_novo = p.pesquisar("GTA 6", "noticias")
    assert primeiras[0].numero == 1 and de_novo[0].numero == 1   # a mesma fonte, o mesmo número
    resposta = json.loads(p.executar("pesquisar", {"consulta": "mais", "tipo": "fatos"}))
    assert "limite de 2 buscas" in resposta["erro"]               # o erro vai como texto
    assert p.executar("ler", {"link": "https://jornal.exemplo/gta"}).startswith("A Rockstar")
    assert "limite de 1 leituras" in json.loads(p.executar("ler", {"link": "x"}))["erro"]
    assert [f["ferramenta"] for f in p.feitas] == ["pesquisar", "pesquisar", "ler"]
    assert p.para_o_pedido().startswith("[1] jornal.exemplo, 2026-10-21: GTA 6 vende")


def test_a_pesquisa_falsa_dos_testes():
    assert pesquisa.falsa()
    r = pesquisa.noticias("céu azul")
    assert r[0].fonte == "Jornal" and r[0].link.startswith("https://exemplo.org/")


class TestAIAQuePesquisa:
    @pytest.fixture
    def sem_falsa(self, monkeypatch):
        monkeypatch.delenv(ia.VARIAVEL_FALSA, raising=False)
        monkeypatch.delenv(ia.VARIAVEL_DA_CHAVE, raising=False)

    def test_a_ia_local_pede_uma_busca_e_responde(self, sem_falsa, monkeypatch):
        from editor import ia_local

        voltas: list[list[dict]] = []

        def conversar(mensagens, *, ferramentas=(), temperatura=0.3, max_tokens=2000):
            voltas.append(list(mensagens))
            if len(voltas) == 1:
                assert ferramentas == pesquisa.FERRAMENTAS
                return {"content": "", "tool_calls": [{"id": "1", "function": {
                    "name": "pesquisar", "arguments": json.dumps({"consulta": "GTA 6",
                                                                  "tipo": "noticias"})}}]}
            return {"content": "- O jogo sai em novembro [1]"}

        monkeypatch.setattr(ia_local, "instalado", lambda: True)
        monkeypatch.setattr(ia_local, "conversar", conversar)
        p = pesquisa.Pesquisa()
        notas = ia.pesquisar_notas("o sistema", "o tema", p)
        assert notas == "- O jogo sai em novembro [1]"
        assert voltas[1][-1]["role"] == "tool" and "o que se sabe" in voltas[1][-1]["content"]
        assert p.feitas[0]["consulta"] == "GTA 6"

    def test_o_gemini_pede_uma_busca_e_responde(self, sem_falsa, monkeypatch):
        monkeypatch.setenv(ia.VARIAVEL_DA_CHAVE, "AIzaSyTESTE-chave-de-mentira-123456")
        corpos: list[dict] = []

        def gemini(pedido: httpx.Request) -> httpx.Response:
            corpos.append(json.loads(pedido.content))
            if len(corpos) == 1:
                partes = [{"functionCall": {"name": "pesquisar",
                                            "args": {"consulta": "GTA 6", "tipo": "fatos"}}}]
            else:
                partes = [{"text": "pensando", "thought": True}, {"text": "- Fato [1]"}]
            return httpx.Response(200, json={"candidates": [{"content": {"role": "model",
                                                                         "parts": partes}}]})

        p = pesquisa.Pesquisa()
        notas = ia.pesquisar_notas("o sistema", "o tema", p,
                                   transporte=httpx.MockTransport(gemini))
        assert notas == "- Fato [1]" and len(corpos) == 2
        nomes = [f["name"] for f in corpos[0]["tools"][0]["functionDeclarations"]]
        assert nomes == ["pesquisar", "ler"]
        resposta = corpos[1]["contents"][-1]["parts"][0]["functionResponse"]
        assert resposta["name"] == "pesquisar" and "Wikipédia" in resposta["response"]["resultado"]


def test_o_roteiro_pelo_tema_com_as_fontes():
    r = escrita.escrever("GTA 6 e a pré-venda", 30, pesquisar=True)
    assert r.por == "falsa" and len(r.fontes) == 4
    assert {f["fonte"] for f in r.fontes} == {"Jornal", "Wikipédia"}
    assert [b["tipo"] for b in r.buscas] == ["noticias", "fatos"]   # a primeira é do Editai
    assert r.para_dict()["fontes"][0]["numero"] == 1
