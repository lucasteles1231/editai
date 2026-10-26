"""
As fotos achadas pelo que é dito (editor/fotos.py): os blocos do roteiro, a busca pela IA ou
pelas palavras, a licença conferida no Openverse (BY-SA, NC e ND de fora), a triagem pelo texto,
o auditor escolhendo entre as candidatas, os créditos e a pasta pronta para ser uma biblioteca de
cenas. O Openverse é um transporte falso do httpx; as fotos falsas (``EDITOR_FOTOS=falso``) valem
nos outros testes. O auditor dos testes daqui lê a nota na cor da foto.
"""
from __future__ import annotations

import io
import itertools
import json
from pathlib import Path

import httpx
import numpy as np
import pytest
from PIL import Image

from editor import auditor, cenas, fotos, ia, pexels

ROTEIRO = ("Por que o céu é azul de dia e vermelho no fim da tarde?\n\n"
           "A luz do Sol tem todas as cores. Quando ela atravessa o ar, o azul se espalha mais.\n\n"
           "No fim da tarde, a luz faz um caminho mais longo. O azul se perde, e sobra o "
           "vermelho. E você, já tinha reparado nisso?")


def _jpeg(largura: int = 1600, altura: int = 900, cor=(40, 90, 200)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (largura, altura), cor).save(buf, "JPEG")
    return buf.getvalue()


def _resultado(k: int, licenca: str = "by", titulo: str = "", largura: int = 1600,
               tags: tuple[str, ...] = ()) -> dict:
    return {"id": f"id{k}", "title": titulo or f"Céu {k}", "url": f"https://img.exemplo/{k}.jpg",
            "creator": f"Autora {k}", "license": licenca, "license_version": "2.0",
            "license_url": f"https://creativecommons.org/licenses/{licenca}/2.0/",
            "foreign_landing_url": f"https://www.flickr.com/photos/x/{k}", "source": "flickr",
            "width": largura, "height": 900, "tags": [{"name": t} for t in tags]}


class _Rede:
    """O Openverse e os servidores das fotos, imitados. Os resultados podem vir por busca, e cada
    foto, numa cor (a nota e a cena, para o auditor dos testes)."""

    def __init__(self, resultados: list[dict] | dict[str, list[dict]],
                 cores: dict[str, tuple] | None = None):
        self.resultados = resultados
        self.cores = cores or {}
        self.buscas: list[dict] = []

    def __call__(self, pedido: httpx.Request) -> httpx.Response:
        if pedido.url.host == "api.openverse.org":
            self.buscas.append(dict(pedido.url.params))
            r = self.resultados
            if isinstance(r, dict):
                r = r.get(pedido.url.params["q"], [])
            return httpx.Response(200, json={"results": r})
        cor = self.cores.get(str(pedido.url), (40, 90, 200))
        return httpx.Response(200, content=_jpeg(cor=cor), headers={"content-type": "image/jpeg"})

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
    assert {"buscando", "conferindo"} <= {e for e, _k, _n in etapas}
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


# ── o auditor ────────────────────────────────────────────────────────────


def _cor(nota: float, cena: int) -> tuple[int, int, int]:
    """A cor de uma foto para o auditor dos testes: o vermelho é a nota (150 = 0,15), e o verde,
    a cena (duas fotos com o mesmo verde são a mesma cena)."""
    return round(nota * 1000), cena * 40, 0


@pytest.fixture
def pela_cor(monkeypatch):
    """O auditor que lê a nota e a cena na cor da foto. Guarda os textos que recebeu."""
    textos: list[str] = []

    def avaliar(imagens, texto):
        textos.append(texto)
        notas, vetores = [], []
        for img in imagens:
            r, g, _b = np.asarray(img.convert("RGB"), dtype=np.float32).mean(axis=(0, 1))
            notas.append(round(float(r) / 1000, 3))
            v = np.zeros(8, np.float32)
            v[round(float(g) / 40) % 8] = 1.0
            vetores.append(v)
        return auditor.Notas(notas, np.array(vetores))

    monkeypatch.setattr(auditor, "avaliar", avaliar)
    return textos


def _candidatas(notas: list[float], cenas_: list[int] | None = None) -> tuple[list[dict], dict]:
    resultados = [_resultado(k) for k in range(len(notas))]
    cenas_ = cenas_ or list(range(len(notas)))
    cores = {r["url"]: _cor(n, c) for r, n, c in zip(resultados, notas, cenas_, strict=True)}
    return resultados, cores


def _autoras(pasta) -> list[str]:
    linhas = (pasta / "creditos.txt").read_text(encoding="utf-8").splitlines()[2:]
    return [linha.split(" por ")[1].split(",")[0] for linha in linhas]


def test_o_auditor_fica_com_as_que_mostram_o_trecho(de_verdade, pela_cor, tmp_path):
    """Antes ficavam as 2 primeiras da busca; agora, as 2 de nota mais alta, acima do piso. O
    terceiro trecho só tem as de nota baixa, e fica sem foto."""
    resultados, cores = _candidatas([0.02, 0.15, 0.04, 0.12, 0.10, 0.08])
    rede = _Rede(resultados, cores)
    etapas: list[str] = []
    achado = fotos.achar(ROTEIRO, tmp_path / "f", transporte=rede.transporte,
                         progresso=lambda e, k, n: etapas.append(e))
    assert _autoras(tmp_path / "f") == ["Autora 1", "Autora 3", "Autora 4", "Autora 5"]
    assert achado.sem_foto == [2] and achado.conferidas
    assert achado.olhadas == 6 + 4 + 2 and achado.recusadas == 2 + 2 + 2
    assert "conferindo" in etapas and "baixando" not in etapas
    assert "O auditor olhou 12 fotos (6 não mostravam o trecho)" in achado.resumo()
    # sem a IA, o que a foto tem de mostrar é a própria busca (as palavras do trecho)
    assert pela_cor[0] == fotos.termo_pelas_palavras(fotos.blocos(ROTEIRO)[0])


def test_a_mesma_cena_nao_entra_duas_vezes(de_verdade, pela_cor, tmp_path):
    # a 0 e a 1 são a mesma cena (o banco devolve várias fotos da mesma sessão)
    resultados, cores = _candidatas([0.15, 0.14, 0.10, 0.09], cenas_=[1, 1, 2, 3])
    fotos.achar(ROTEIRO, tmp_path / "f", transporte=_Rede(resultados, cores).transporte)
    autoras = _autoras(tmp_path / "f")
    assert autoras[:2] == ["Autora 0", "Autora 2"]
    assert "Autora 1" not in autoras              # nem no trecho seguinte


def test_sem_nenhuma_boa_vem_a_busca_de_reserva(de_verdade, pela_cor, monkeypatch, tmp_path):
    monkeypatch.delenv(ia.VARIAVEL_FALSA, raising=False)
    monkeypatch.setenv(ia.VARIAVEL_DA_CHAVE, "AIzaSyTESTE-chave-de-mentira-123456")
    ruins, cores = _candidatas([0.02, 0.03])
    boas = [_resultado(k) for k in (7, 8)]
    cores |= {r["url"]: _cor(n, c) for r, n, c in zip(boas, (0.14, 0.11), (5, 6), strict=True)}
    rede = _Rede({"blue sky": ruins, "sky": boas}, cores)

    def tudo(pedido: httpx.Request) -> httpx.Response:
        if pedido.url.host == "generativelanguage.googleapis.com":
            texto = json.dumps({"fotos": [{"k": 0, "busca": "blue sky", "reserva": "sky",
                                           "descricao": "Um céu azul de dia"}]})
            return httpx.Response(200, json={"candidates": [{"content": {"parts": [
                {"text": texto}]}, "finishReason": "STOP"}]})
        return rede(pedido)

    achado = fotos.achar(ROTEIRO.split("\n\n")[0], tmp_path / "f",
                         transporte=httpx.MockTransport(tudo))
    assert [b["q"] for b in rede.buscas] == ["blue sky", "sky"]
    assert _autoras(tmp_path / "f") == ["Autora 7", "Autora 8"] and not achado.sem_foto
    # com a IA, a foto tem de mostrar a descrição que ela imaginou
    assert pela_cor == ["Um céu azul de dia", "Um céu azul de dia"]


def test_nenhuma_boa_no_roteiro_inteiro_fica_a_mais_proxima(de_verdade, pela_cor, tmp_path):
    resultados, cores = _candidatas([0.02, 0.05, 0.01])
    achado = fotos.achar(ROTEIRO, tmp_path / "f",
                         transporte=_Rede(resultados, cores).transporte)
    # a melhor (a 1) era a mesma nos três trechos: entra uma vez, e os vizinhos cobrem
    assert _autoras(tmp_path / "f") == ["Autora 1"] and achado.sem_foto == [1, 2]
    assert "ficaram as que mais se aproximam" in achado.resumo()


def test_sem_o_auditor_ficam_as_primeiras(de_verdade, monkeypatch, tmp_path):
    def nao_chama(*_a, **_k):
        raise AssertionError("o auditor não devia ser chamado")

    monkeypatch.setattr(auditor, "avaliar", nao_chama)
    resultados, cores = _candidatas([0.02, 0.15, 0.04, 0.12])
    rede = _Rede(resultados, cores)
    achado = fotos.achar(ROTEIRO, tmp_path / "a", conferir=False, transporte=rede.transporte)
    assert _autoras(tmp_path / "a") == ["Autora 0", "Autora 1", "Autora 2", "Autora 3"]
    assert not achado.conferidas and achado.resumo() == ""
    # e o auditor que não carrega (sem internet na primeira vez) avisa e deixa as primeiras
    monkeypatch.setattr(auditor, "preparar", lambda *_a: False)
    achado = fotos.achar(ROTEIRO, tmp_path / "b", transporte=rede.transporte)
    assert _autoras(tmp_path / "b")[:2] == ["Autora 0", "Autora 1"]
    assert "não carregou" in achado.resumo()


def test_o_pexels_vai_pela_previa(de_verdade, monkeypatch, tmp_path):
    """A nota sai da prévia do Pexels (uns 40 KB); a foto grande só baixa para a escolhida."""
    monkeypatch.setenv(pexels.VARIAVEL_FALSA, "falso")
    ids = itertools.count(1)

    def buscar(consulta, orientacao="paisagem", *, transporte=None):
        return [pexels.Foto(id=n, largura=1600, altura=900, autor=f"Fotógrafo {n}", autor_url="",
                            pagina=f"https://www.pexels.com/foto/{n}/", alt=f"{consulta} {n}",
                            previa=f"https://images.pexels.com/{n}/previa.jpg",
                            grande=f"https://images.pexels.com/{n}/grande.jpg")
                for n in (next(ids) for _ in range(6))]

    pedidos: list[str] = []

    def baixar(foto_id, tamanho="previa", *, transporte=None):
        pedidos.append(tamanho)
        return _jpeg(320, 180) if tamanho == "previa" else _jpeg()

    monkeypatch.setattr(pexels, "buscar", buscar)
    monkeypatch.setattr(pexels, "baixar", baixar)
    achado = fotos.achar(ROTEIRO, tmp_path / "p", transporte=_Rede([]).transporte)
    assert len(achado.cenas) == 6
    assert pedidos.count("grande") == 6 and pedidos.count("previa") == 3 * 6


# ── as fotos no vídeo ────────────────────────────────────────────────────

TRES = ("Por que o céu é azul de dia? A pergunta parece simples demais.\n\n"
        "A luz do Sol tem todas as cores misturadas. O ar espalha mais o azul.\n\n"
        "No fim da tarde a luz atravessa mais ar. Sobra o vermelho no horizonte.")


def _biblioteca_dos_trechos(*trechos: int) -> cenas.Biblioteca:
    """Duas fotos para cada trecho pedido (f1 e f2 no 1, f3 e f4 no 2…)."""
    return cenas.Biblioteca([
        cenas.Cena(f"f{2 * (t - 1) + i}", Path(f"f{2 * (t - 1) + i}.jpg"), "uma foto",
                   duracao=cenas.FOTO_S, tipo="imagem", trecho=t)
        for t in trechos for i in (1, 2)])


def _falado(texto: str, passo: float = 0.4) -> list:
    from editor.transcricao import Palavra

    return [Palavra(w, round(i * passo, 3), round(i * passo + 0.3, 3))
            for i, w in enumerate(texto.split())]


def _trechos_por_bloco(blocos, escolhas, b: cenas.Biblioteca) -> list[set[int]]:
    por_id = b.por_id()
    return [{por_id[i].trecho for i in ids} for ids in escolhas]


def test_cada_foto_entra_no_trecho_dela():
    b = _biblioteca_dos_trechos(1, 2, 3)
    falado = _falado(TRES)
    blocos = cenas.blocos_da_fala(falado, falado[-1].fim + 0.5)
    escolhas = fotos.pelos_trechos(blocos, b, falado, TRES)
    assert escolhas is not None and len(escolhas) == len(blocos)
    trechos = _trechos_por_bloco(blocos, escolhas, b)
    assert all(len(t) == 1 for t in trechos)        # um bloco, um trecho
    assert [min(t) for t in trechos] == sorted(min(t) for t in trechos)
    assert {min(t) for t in trechos} == {1, 2, 3}
    # o bloco que fala do vermelho mostra as fotos do terceiro trecho
    final = next(k for k, bl in enumerate(blocos) if "vermelho" in bl.texto)
    assert trechos[final] == {3}


def test_a_frase_cortada_e_o_trecho_sem_foto():
    """O "Quanto tempo?" tirou o segundo parágrafo da fala: os blocos seguem o primeiro e o
    terceiro trechos. E o trecho sem foto fica com as do anterior."""
    b = _biblioteca_dos_trechos(1, 2, 3)
    paragrafos = TRES.split("\n\n")
    falado = _falado(f"{paragrafos[0]} {paragrafos[2]}")
    blocos = cenas.blocos_da_fala(falado, falado[-1].fim)
    trechos = _trechos_por_bloco(blocos, fotos.pelos_trechos(blocos, b, falado, TRES), b)
    assert {min(t) for t in trechos} == {1, 3}
    sem_o_dois = _biblioteca_dos_trechos(1, 3)
    falado = _falado(TRES)
    blocos = cenas.blocos_da_fala(falado, falado[-1].fim)
    trechos = _trechos_por_bloco(blocos, fotos.pelos_trechos(blocos, sem_o_dois, falado, TRES),
                                 sem_o_dois)
    meio = next(k for k, bl in enumerate(blocos) if "espalha" in bl.texto)
    assert trechos[meio] == {1}


def test_sem_os_trechos_a_escolha_e_a_de_sempre():
    falado = _falado(TRES)
    blocos = cenas.blocos_da_fala(falado, falado[-1].fim)
    b = _biblioteca_dos_trechos(1, 2, 3)
    b.cenas[0].trecho = 0                            # uma cena que não é foto achada
    assert fotos.pelos_trechos(blocos, b, falado, TRES) is None
    outra = _falado("Hoje o assunto é outro: um jogo novo, o trailer e a data de lançamento.")
    assert fotos.pelos_trechos(cenas.blocos_da_fala(outra, 6.0), _biblioteca_dos_trechos(1, 2),
                               outra, TRES) is None


def test_o_roteiro_do_video_nao_pede_as_cenas_das_fotos():
    from editor import roteiro

    b = _biblioteca_dos_trechos(1, 2, 3)
    falado = _falado(TRES)
    duracao = falado[-1].fim + 0.5
    r = roteiro.escrever(falado, duracao, biblioteca=b, cartoes=False, idioma="pt",
                         nomes_de_icones=[], texto_falado=TRES)
    blocos = cenas.blocos_da_fala(falado, duracao)
    assert r.por == "trechos" and r.pedidos == 0
    assert r.escolhas == fotos.pelos_trechos(blocos, b, falado, TRES)
    # com os cartões, a IA (a falsa dos testes) só escreve os cartões
    r = roteiro.escrever(falado, duracao, biblioteca=b, cartoes=True, idioma="pt",
                         nomes_de_icones=["estrela"], texto_falado=TRES)
    assert r.por == "falsa" and r.cartoes
    assert r.escolhas == fotos.pelos_trechos(blocos, b, falado, TRES)
