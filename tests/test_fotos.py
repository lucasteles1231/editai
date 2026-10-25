"""
As fotos achadas pelo que é dito (editor/fotos.py): os blocos do roteiro, a busca pela IA ou
pelas palavras, a licença conferida no Openverse (BY-SA, NC e ND de fora), a triagem pelo texto,
os créditos e a pasta pronta para ser uma biblioteca de cenas. O Openverse é um transporte falso
do httpx; as fotos falsas (``EDITOR_FOTOS=falso``) valem nos outros testes.
"""
from __future__ import annotations

import io
import json

import httpx
import pytest
from PIL import Image

from editor import cenas, fotos, ia, pexels

ROTEIRO = ("Por que o céu é azul de dia e vermelho no fim da tarde?\n\n"
           "A luz do Sol tem todas as cores. Quando ela atravessa o ar, o azul se espalha mais.\n\n"
           "No fim da tarde, a luz faz um caminho mais longo. O azul se perde, e sobra o "
           "vermelho. E você, já tinha reparado nisso?")


def _jpeg(largura: int = 1600, altura: int = 900) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (largura, altura), (40, 90, 200)).save(buf, "JPEG")
    return buf.getvalue()


def _resultado(k: int, licenca: str = "by", titulo: str = "", largura: int = 1600,
               tags: tuple[str, ...] = ()) -> dict:
    return {"id": f"id{k}", "title": titulo or f"Céu {k}", "url": f"https://img.exemplo/{k}.jpg",
            "creator": f"Autora {k}", "license": licenca, "license_version": "2.0",
            "license_url": f"https://creativecommons.org/licenses/{licenca}/2.0/",
            "foreign_landing_url": f"https://www.flickr.com/photos/x/{k}", "source": "flickr",
            "width": largura, "height": 900, "tags": [{"name": t} for t in tags]}


class _Rede:
    """O Openverse e os servidores das fotos, imitados."""

    def __init__(self, resultados: list[dict]):
        self.resultados = resultados
        self.buscas: list[dict] = []

    def __call__(self, pedido: httpx.Request) -> httpx.Response:
        if pedido.url.host == "api.openverse.org":
            self.buscas.append(dict(pedido.url.params))
            return httpx.Response(200, json={"results": self.resultados})
        return httpx.Response(200, content=_jpeg(), headers={"content-type": "image/jpeg"})

    @property
    def transporte(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)


@pytest.fixture
def de_verdade(monkeypatch):
    monkeypatch.delenv(fotos.VARIAVEL_FALSA, raising=False)
    monkeypatch.delenv(pexels.VARIAVEL_FALSA, raising=False)       # sem a chave: só o Openverse
    monkeypatch.setattr(fotos, "ENTRE_PEDIDOS_S", 0)


def test_os_blocos_do_roteiro():
    b = fotos.blocos(ROTEIRO)
    assert b[0] == "Por que o céu é azul de dia e vermelho no fim da tarde?"
    assert len(b) == 3
    longo = " ".join(["Uma frase de sete palavras bem certinhas aqui."] * 6)
    partes = fotos.blocos(longo)
    assert len(partes) > 1 and all(len(p.split()) <= fotos.PALAVRAS_POR_BLOCO for p in partes)


def test_a_busca_pelas_palavras_sem_a_ia():
    assert fotos.termo_pelas_palavras("Quando ela atravessa o ar, o azul se espalha mais.") \
        == "atravessa espalha azul"


def test_a_licenca_e_a_triagem(de_verdade):
    rede = _Rede([_resultado(1, "by-sa"), _resultado(2, "by-nc"), _resultado(3, "nd"),
                  _resultado(4, "by", titulo="Logo da NASA"),
                  _resultado(5, "cc0", largura=640),
                  _resultado(6, "cc0", tags=("diagram",)),
                  _resultado(7, "by", titulo="Texture of the sky"),
                  _resultado(8, "pdm")])
    achadas = fotos.procurar("blue sky", transporte=rede.transporte)
    assert [a.url.rsplit("/", 1)[-1] for a in achadas] == ["7.jpg", "8.jpg"]
    params = rede.buscas[0]
    assert params["license"] == "cc0,pdm,by" and params["q"] == "blue sky"
    assert params["aspect_ratio"] == "wide" and params["mature"] == "false"


def test_com_o_pexels_trazendo_o_bastante_o_openverse_fica_de_fora(de_verdade, monkeypatch):
    monkeypatch.setattr(fotos, "_do_pexels", lambda termo, orientacao, transporte=None: [
        fotos.Achada(url=f"https://pexels/{k}.jpg", titulo="", autor="A", licenca="pexels",
                     versao="", link="", licenca_url="", fonte="Pexels")
        for k in range(fotos.POR_BLOCO * 2)])
    rede = _Rede([_resultado(1)])
    assert len(fotos.procurar("blue sky", transporte=rede.transporte)) == fotos.POR_BLOCO * 2
    assert rede.buscas == []
    # com menos, o Openverse completa
    monkeypatch.setattr(fotos, "_do_pexels", lambda termo, orientacao, transporte=None: [])
    assert len(fotos.procurar("blue sky", transporte=rede.transporte)) == 1
    assert len(rede.buscas) == 1


def test_acha_baixa_e_monta_a_biblioteca(de_verdade, tmp_path):
    rede = _Rede([_resultado(k) for k in range(4)])
    pasta = tmp_path / "fotos" / "ceu"
    etapas = []
    achado = fotos.achar(ROTEIRO, pasta, tema="o céu", transporte=rede.transporte,
                         progresso=lambda e, k, n: etapas.append((e, k, n)))
    # 3 trechos, 2 fotos cada, sem repetir a mesma foto em dois trechos: o terceiro fica sem
    assert len(achado.cenas) == 4 and achado.sem_foto == [2]
    assert {"buscando", "baixando"} <= {e for e, _k, _n in etapas}
    matriz = json.loads((pasta / "cenas.json").read_text(encoding="utf-8"))
    assert [c["arquivo"] for c in matriz] == [f"foto-00{k}.jpg" for k in range(1, 5)]
    creditos = (pasta / "creditos.txt").read_text(encoding="utf-8")
    assert "CC BY 2.0" in creditos and "Autora 0" in creditos and "flickr.com" in creditos
    # a pasta vale como uma biblioteca de cenas comum
    b = cenas.ler_matriz(json.dumps(matriz), cenas.clipes_da_pasta(pasta))
    assert len(b.cenas) == 4 and all(c.imagem for c in b.cenas)


def test_a_ia_escreve_as_buscas_em_ingles(de_verdade, monkeypatch, tmp_path):
    monkeypatch.delenv(ia.VARIAVEL_FALSA, raising=False)
    monkeypatch.setenv(ia.VARIAVEL_DA_CHAVE, "AIzaSyTESTE-chave-de-mentira-123456")

    def gemini(pedido: httpx.Request) -> httpx.Response:
        if pedido.url.host == "generativelanguage.googleapis.com":
            texto = json.dumps({"fotos": [{"k": 0, "busca": "blue sky sunny day",
                                           "descricao": "Um céu azul de dia"},
                                          {"k": 9, "busca": "fora", "descricao": "fora"}]})
            return httpx.Response(200, json={"candidates": [{"content": {"parts": [
                {"text": texto}]}, "finishReason": "STOP"}]})
        return httpx.Response(500)

    vistos: list[str] = []
    lista, pedidos = fotos.buscas(fotos.blocos(ROTEIRO), "céu", transporte=httpx.MockTransport(
        lambda p: (vistos.append(p.url.path.rsplit("/", 1)[-1]), gemini(p))[1]))
    assert pedidos == 1
    # o pedido simples vai primeiro ao modelo leve, que responde em segundos
    assert vistos == [f"{ia.MODELOS_LEVES[0]}:generateContent"]
    assert lista[0].termo == "blue sky sunny day" and lista[0].descricao == "Um céu azul de dia"
    assert lista[1].termo == fotos.termo_pelas_palavras(lista[1].bloco)   # o que faltou


def test_nada_achado_avisa(de_verdade, tmp_path):
    with pytest.raises(fotos.SemFotos, match="Não achei"):
        fotos.achar(ROTEIRO, tmp_path / "x", transporte=_Rede([]).transporte)
    with pytest.raises(fotos.SemFotos, match="vazio"):
        fotos.achar("  ", tmp_path / "y")


def test_as_fotos_falsas_dos_testes(tmp_path):
    achado = fotos.achar(ROTEIRO, tmp_path / "z")
    assert len(achado.cenas) == 6 and not achado.sem_foto
    with Image.open(tmp_path / "z" / "foto-001.jpg") as img:
        assert max(img.size) <= fotos.LADO_GUARDADO
