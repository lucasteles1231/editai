"""
O avatar (``editor/avatar.py``): o catálogo, guardar e baixar, o Gemini escolhendo pela foto
(com um transporte falso), a boca pelas sílabas, a pose de cada frase e a camada da montagem.

Os quadros dos testes são desenhos simples feitos aqui (o desenhista de verdade roda na página,
e o teste do navegador cobre ele): um corpo com a cor da pose, uma boca com a cor da boca e um
braço à direita, para dar para ver o espelho.
"""
from __future__ import annotations

import base64
import io
import json
import wave
import zipfile
from itertools import pairwise
from pathlib import Path

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from editor import avatar, ia, montagem, render, saida, servidor
from editor.opcoes import OpcoesDeEdicao
from editor.plano import Bloco
from editor.transcricao import Palavra
from tests.conftest import fazer_video, ler_info

LADO = 900
COR_DA_BOCA = {"fechada": (20, 20, 20), "meia": (120, 120, 120), "aberta": (230, 30, 30)}


def _quadro(pose: str, boca: str) -> np.ndarray:
    k = avatar.poses().index(pose)
    q = np.zeros((LADO, LADO, 4), np.uint8)
    q[150:750, 300:600] = (40 + k * 15, 90, 200 - k * 10, 255)          # o corpo, na cor da pose
    q[330:390, 420:480] = (*COR_DA_BOCA[boca], 255)                    # a boca
    q[300:340, 600:820] = (250, 200, 0, 255)                           # o braço, à direita
    return q


def _png(q: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(q, "RGBA").save(buf, "PNG")
    return buf.getvalue()


def _grade(arquivo: str, por_grupo: bool = False) -> dict:
    """Os pixels de uma parte: {(y, x): classe} (ou um desses por grupo)."""
    import re
    from importlib.resources import files

    partes = files("editor").joinpath("recursos", "personagem", "partes")
    texto = partes.joinpath(*arquivo.split("/")).read_text()
    grupos: dict = {}
    for camada, corpo in re.findall(r'<g data-camada="([^"]+)"[^>]*>(.*?)</g>', texto, re.S):
        g = grupos.setdefault(camada, {})
        for cls, d in re.findall(r'class="([^"]+)" d="([^"]+)"', corpo):
            for x, y, n in re.findall(r"M(\d+) (\d+)h(\d+)", d):
                for k in range(int(n)):
                    g[(int(y), int(x) + k)] = cls
    if por_grupo:
        return grupos
    return {k: v for g in grupos.values() for k, v in g.items()}


def _extracao() -> dict:
    from importlib.resources import files

    partes = files("editor").joinpath("recursos", "personagem", "partes")
    return json.loads(partes.joinpath("extracao.json").read_text())


def padrao_camadas() -> list[str]:
    return avatar.padrao()["camadas"]


def _quadros() -> dict[str, bytes]:
    return {f"{p}_{b}.png": _png(_quadro(p, b)) for p in avatar.poses() for b in avatar.bocas()}


def _salvar(nome: str = "Lucas Teles") -> dict:
    return avatar.salvar(nome, {"cabelo": "topete", "cores": {"pele": "#e2a57c"}}, _quadros())


def _silabas(caminho: Path, *, n: int, por_segundo: float = 4.0, inicio: float = 0.5,
             fracas: tuple[int, ...] = ()) -> Path:
    """Uma fala de mentira: ``n`` sílabas (um tom com envelope de seno), umas mais fracas."""
    taxa = 16_000
    total = inicio + n / por_segundo + 1.0
    t = np.arange(round(total * taxa)) / taxa
    som = np.zeros_like(t)
    passo = 1 / por_segundo
    for i in range(n):
        a0 = inicio + i * passo
        dentro = (t >= a0) & (t < a0 + passo * 0.8)
        forca = 0.35 if i in fracas else 1.0
        som[dentro] += forca * 0.5 * np.sin(np.pi * (t[dentro] - a0) / (passo * 0.8)) \
            * np.sin(2 * np.pi * 180 * t[dentro])
    with wave.open(str(caminho), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taxa)
        w.writeframes((som * 32767).astype("<i2").tobytes())
    return caminho


def _ler_wav(caminho: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(caminho)) as w:
        return (np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(np.float64),
                w.getframerate())


# ── o catálogo ───────────────────────────────────────────────────────────


class TestOCatalogo:
    def test_toda_parte_do_catalogo_existe_e_bate_o_hash(self):
        import hashlib
        from importlib.resources import files

        partes = files("editor").joinpath("recursos", "personagem", "partes")
        cat = avatar.catalogo()
        for rel, info in cat["arquivos"].items():
            dados = partes.joinpath(*rel.split("/")).read_bytes()
            assert hashlib.sha256(dados).hexdigest() == info["sha256"], rel
        for categoria, c in cat["categorias"].items():
            for o in c["opcoes"]:
                assert f"{categoria}/{o['id']}.svg" in cat["arquivos"]
                assert o["pt"] and o["en"]

    def test_as_poses_os_bracos_e_as_bocas_de_cada_pose_existem(self):
        arquivos = avatar.catalogo()["arquivos"]
        for pose, p in avatar.padrao()["poses"].items():
            if pose != "neutro":
                assert f"bracos/ia.{p['bracos']}.svg" in arquivos, pose
            if p["boca"] != "sorriso":                # o sorriso é o do manequim
                assert f"boca/ia.{p['boca']}.svg" in arquivos, pose
        for boca in ("meia", "aberta"):
            assert f"boca/ia.{boca}.svg" in arquivos

    def test_as_bocas_desenhadas_sao_simetricas(self):
        """As bocas são desenhadas em código (as da IA, reduzidas à grade, viravam riscos): cada
        uma é simétrica, centrada no rosto, e o sorriso das poses comuns também é uma parte."""
        centros = set()
        for estado in ("sorriso", "neutra", "o", "rindo", "meia", "aberta"):
            g = _grade(f"boca/ia.{estado}.svg")
            xs = sorted({x for (_y, x) in g})
            centros.add((xs[0] + xs[-1]) / 2)
            for y in {y for (y, _x) in g}:
                linha = {x: c for (yy, x), c in g.items() if yy == y}
                for x, c in linha.items():
                    assert linha.get(xs[0] + xs[-1] - x) == c, (estado, y, x)
        assert len(centros) == 1, centros

    def test_o_chapeu_corta_o_cabelo(self):
        from importlib.resources import files

        partes = files("editor").joinpath("recursos", "personagem", "partes", "acessorio")
        for chapeu in ("bone", "gorro"):
            texto = partes.joinpath(f"{chapeu}.svg").read_text()
            assert 'data-camada="acessorio" data-pronto="sim" data-cobre="cabelo"' in texto
        assert "data-cobre" not in partes.joinpath("fone.svg").read_text()

    def test_a_cor_do_olho_pinta_a_iris(self):
        """A íris é marrom-escura no Nano Banana e caía no contorno: a cor escolhida não mudava
        nada. Agora ela é "olho", no manequim e em cada estado dos olhos."""
        # a peça de um estado só guarda o que mudou: a íris que andou (o resto vem do manequim)
        for arq, minimo in (("cabeca/manequim.svg", 10), ("olhos/ia.lado.svg", 2),
                            ("olhos/ia.cima.svg", 2), ("olhos/ia.arregalado.svg", 2)):
            g = _grade(arq)
            assert sum(c.startswith("olho") for c in g.values()) >= minimo, arq

    def test_a_cabeca_em_cabeca_pescoco_e_corpo(self):
        """A cabeça não passa do queixo: as linhas da gola do suéter iam por cima de toda roupa
        escolhida. O pescoço fica numa camada abaixo do corpo, e a gola nova o cobre."""
        info = _extracao()
        grupos = _grade("cabeca/manequim.svg", por_grupo=True)
        assert set(grupos) == {"cabeca", "pescoco", "corpo"}
        queixo = info["marcos"]["queixo"]
        assert max(y for (y, _x) in grupos["cabeca"]) <= queixo
        assert min(y for (y, _x) in grupos["pescoco"]) > queixo
        cores = {c.split("-")[0] for c in grupos["pescoco"].values()}
        assert cores <= {"pele", "contorno"}
        assert padrao_camadas().index("pescoco") < padrao_camadas().index("corpo")

    def test_sobrancelha_so_na_sobrancelha(self):
        """O brilho da careca e o desenho da orelha eram "sobrancelha" e mudavam com a cor do
        cabelo."""
        a, b = _extracao()["marcos"]["sobrancelha"]
        g = _grade("cabeca/manequim.svg")
        linhas = {y for (y, _x), c in g.items() if c.startswith("sobrancelha")}
        assert linhas <= set(range(a - 3, b + 3))

    def test_a_cabeca_em_capsula(self):
        """O alto da cabeça com a largura do rosto, como no exemplo do dono (no manequim gerado, ele
        era bem mais largo: uma lâmpada), e o queixo de antes, que o dono aprovou (alargar o
        maxilar deixou o queixo quadrado)."""
        info = _extracao()["capsula"]
        g = _grade("cabeca/manequim.svg", por_grupo=True)["cabeca"]

        def largura(y):
            xs = [x for (yy, x), c in g.items() if yy == y and c == "contorno"]
            return max(xs) - min(xs)

        # até a linha antes da orelha (na de cima dela, o contorno da orelha encosta na cabeça)
        topo = max(largura(y) for y in range(_extracao()["marcos"]["topo"], info["orelha"][0] - 1))
        antes = info["cranio_antes"][1] - info["cranio_antes"][0]
        # o alvo é a linha do rosto; onde o contorno tinha 2 px, o de fora fica uma coluna além
        assert topo <= info["cranio"][1] - info["cranio"][0] + 2 < antes
        assert largura(info["orelha"][1] + 2) >= 0.8 * topo     # o maxilar logo abaixo da orelha
        # o queixo: a pele contínua que passa pelo meio (ao lado do V fica a pele do pescoço)
        y = info["queixo"] - 1
        pele = {x for (yy, x), c in g.items() if yy == y and c.startswith("pele")}
        e = d = round(sum(info["cranio"]) / 2)
        while e - 1 in pele:
            e -= 1
        while d + 1 in pele:
            d += 1
        assert d - e < 0.4 * topo                               # em V, como antes

    def test_a_cupula_lisa_e_a_testa_curta(self):
        """A cúpula do careca sem amassado e mais perto da sobrancelha (o dono, 21/10/2026): a
        borda em degraus limpos de pixel art e simétrica, e a testa como no exemplo dele."""
        info = _extracao()
        g = _grade("cabeca/manequim.svg", por_grupo=True)["cabeca"]
        topo, ate = info["marcos"]["topo"], info["capsula"]["orelha"][0] - 2
        esq = [min(x for (yy, x) in g if yy == y) for y in range(topo, ate + 1)]
        dir_ = [max(x for (yy, x) in g if yy == y) for y in range(topo, ate + 1)]
        assert len({e + d for e, d in zip(esq, dir_, strict=True)}) == 1, "a cúpula não é simétrica"
        passos = [b - a for a, b in pairwise(esq)]
        assert all(p <= 0 for p in passos), "a borda volta para dentro descendo"
        passos = [-p for p in passos]
        # o degrau largo (mais de 1 pixel por linha) só no começo, seguido, e sem crescer
        largos = [i for i, p in enumerate(passos) if p > 1]
        assert largos == list(range(len(largos)))
        assert all(passos[i] >= passos[i + 1] for i in largos)
        # depois, os trechos retos entre um degrau e outro só crescem (o "1, 0, 1" era o amassado)
        degraus = [i for i, p in enumerate(passos) if p >= 1]
        trechos = [b - a for a, b in pairwise(degraus)]
        assert trechos == sorted(trechos), f"trechos retos {trechos}"
        largura = info["capsula"]["cranio"][1] - info["capsula"]["cranio"][0]
        assert (info["marcos"]["sobrancelha"][0] - topo) / largura <= 0.52   # no exemplo, 0,49

    def test_o_cabelo_sem_furo_mostrando_a_pele(self):
        """Nenhum buraco pequeno e fechado no cabelo acima da sobrancelha: na cúpula nova ele
        mostrava um risco de pele dentro do cabelo (o chanel, 21/10/2026)."""
        from importlib.resources import files

        testa = _extracao()["marcos"]["sobrancelha"][0]
        pasta = files("editor").joinpath("recursos", "personagem", "partes", "cabelo")
        for nome in sorted(p.name for p in pasta.iterdir() if p.name.endswith(".svg")):
            cheio = set(_grade(f"cabelo/{nome}"))
            visto: set = set()
            for inicio in ((y, x) for y in range(testa) for x in range(150)):
                if inicio in cheio or inicio in visto:
                    continue
                buraco, fila = [], [inicio]
                visto.add(inicio)
                while fila:
                    y, x = fila.pop()
                    buraco.append((y, x))
                    for v in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                        dentro = 0 <= v[0] < 150 and 0 <= v[1] < 150
                        if dentro and v not in cheio and v not in visto:
                            visto.add(v)
                            fila.append(v)
                fechado = all(0 < y < testa and 0 < x < 149 for y, x in buraco)
                assert not (fechado and len(buraco) <= 40), \
                    f"{nome}: furo de {len(buraco)} px em {buraco[0]}"

    def test_os_enums_do_pedido_sao_pequenos(self):
        # o enum grande dá 400 genérico nos modelos 3.x (medido em 03/10/2026)
        _texto, esquema = avatar.pedido_das_partes()
        for campo in esquema["properties"].values():
            assert len(campo.get("enum", [])) <= 16

    def test_escolhas_fora_do_catalogo_viram_o_padrao(self):
        e = avatar.escolhas_validas({"cabelo": "moicano", "barba": "cheia", "oculos": 3,
                                     "cores": {"pele": "#ABCDEF", "cabelo": "vermelho",
                                               "barba": ""}})
        padrao_ = avatar.catalogo()["padrao"]
        assert e["cabelo"] == padrao_["cabelo"] and e["barba"] == "cheia"
        assert e["oculos"] == padrao_["oculos"]
        assert e["cores"]["pele"] == "#abcdef"
        assert e["cores"]["cabelo"] == padrao_["cores"]["cabelo"]
        assert e["cores"]["barba"] == ""                       # vazia: a do cabelo
        assert e["cabeca"] == "manequim" and e["bracos"] == "ia"   # as fixas


class TestOsBichos:
    """As cabeças de bicho (o dono, 21–22/10/2026): a cabeça no lugar da do manequim, os olhos e
    as bocas desenhados em código para ela, e a pelagem no espaço da pele."""

    def bichos(self) -> list[str]:
        return [b["id"] for b in avatar.catalogo()["bichos"]]

    def test_cada_bicho_tem_a_cabeca_os_olhos_e_as_bocas(self):
        assert len(self.bichos()) >= 20                         # os 20 da folha do dono
        for b in self.bichos():
            grupos = _grade(f"cabeca/{b}.svg", por_grupo=True)
            assert set(grupos) == {"cabeca", "pescoco", "corpo"}, b
            # a pelagem é "pele": a cor escolhida pinta o bicho (e o pescoço e as mãos das poses)
            assert sum(c.startswith("pele") for c in grupos["cabeca"].values()) > 300, b
            for estado in ("aberto", "lado", "cima", "arregalado", "apertado", "meio"):
                assert _grade(f"olhos/{b}.{estado}.svg"), (b, estado)
            # o olho aberto tem a cor escolhida no de dentro e o brilho branco
            aberto = _grade(f"olhos/{b}.aberto.svg").values()
            assert "olho" in aberto and "branco" in aberto, b

    def test_as_bocas_dos_bichos_sao_simetricas_e_debaixo_do_nariz(self):
        info = {}
        for b in self.bichos():
            centros = set()
            for estado in ("sorriso", "neutra", "o", "meia", "aberta", "rindo"):
                g = _grade(f"boca/{b}.{estado}.svg")
                if not g:
                    # o bico fechado é o próprio bico (o pato, a galinha, o pinguim): falando, abre
                    assert estado in ("sorriso", "neutra"), (b, estado)
                    continue
                xs = sorted({x for (_y, x) in g})
                centros.add((xs[0] + xs[-1]) / 2)
                for (y, x), c in g.items():
                    assert g.get((y, xs[0] + xs[-1] - x)) == c, (b, estado, y, x)
                info[b] = min(y for (y, _x) in g)
            assert len(centros) == 1, (b, centros)
            # a boca começa logo abaixo do nariz: a cabeça é pele ou contorno ali, não vazio
            cabeca = _grade(f"cabeca/{b}.svg", por_grupo=True)["cabeca"]
            assert (info[b], int(centros.pop())) in cabeca, b

    def test_o_bicho_nao_leva_as_partes_da_cabeca_humana(self):
        e = avatar.escolhas_validas({"cabeca": "gato", "cabelo": "afro", "barba": "cheia",
                                     "oculos": "redondos", "acessorio": "bone", "roupa": "jaqueta"})
        assert (e["cabeca"], e["olhos"], e["boca"]) == ("gato", "gato", "gato")
        humanas = ("cabelo", "barba", "oculos", "acessorio", "sobrancelhas")
        assert {e[c] for c in humanas} == {"nenhum"}
        assert e["roupa"] == "jaqueta"                          # a roupa fica
        # um bicho que não existe é a pessoa de sempre
        assert avatar.escolhas_validas({"cabeca": "dragao"})["cabeca"] == "manequim"


# ── guardar, listar e baixar ─────────────────────────────────────────────


class TestGuardar:
    def test_salva_lista_le_e_apaga(self):
        info = _salvar()
        assert info["apelido"] == "lucas-teles"
        assert info["escolhas"]["cabelo"] == "topete"
        assert [a["nome"] for a in avatar.avatares()] == ["Lucas Teles"]
        assert avatar.achar("Lucas Teles") == avatar.achar("lucas-teles") == "lucas-teles"
        caixa = info["caixas"]["neutro"]                     # o corpo e o braço do desenho
        assert caixa == {"x0": round(300 / LADO, 4), "y0": round(150 / LADO, 4),
                         "x1": round(820 / LADO, 4), "y1": round(750 / LADO, 4)}
        assert 0 < info["rosto"]["x0"] < info["rosto"]["x1"] < 1
        assert avatar.quadro("lucas-teles", "rindo_aberta.png").is_file()
        avatar.apagar("lucas-teles")
        assert avatar.avatares() == []
        with pytest.raises(avatar.AvatarInvalido):
            avatar.ler("lucas-teles")

    def test_o_mesmo_nome_substitui(self):
        _salvar()
        info = avatar.salvar("lucas teles", {"cabelo": "afro"}, _quadros())
        assert len(avatar.avatares()) == 1 and info["escolhas"]["cabelo"] == "afro"

    def test_o_pacote(self):
        _salvar()
        z = zipfile.ZipFile(io.BytesIO(avatar.pacote("lucas-teles")))
        nomes = set(z.namelist())
        assert {f"lucas-teles/{n}" for n in avatar.nomes_dos_quadros()} <= nomes
        assert {"lucas-teles/avatar.json", "lucas-teles/padrao.json",
                "lucas-teles/LEIA-ME.txt"} <= nomes
        leia = z.read("lucas-teles/LEIA-ME.txt").decode()
        assert "apontando_lado" in leia and "57%" in leia

    @pytest.mark.parametrize("estraga, erro", [
        (lambda q: q.pop("cafe_meia.png"), "Faltam"),
        (lambda q: q.update({"cafe_meia.png": b"nada"}), "não é uma imagem"),
        (lambda q: q.update({"cafe_meia.png": _png(np.zeros((10, 10, 4), np.uint8))}), "900"),
        (lambda q: q.update({"extra.png": q["cafe_meia.png"]}), "desconhecido"),
    ])
    def test_quadros_que_nao_servem(self, estraga, erro):
        q = _quadros()
        estraga(q)
        with pytest.raises(avatar.AvatarInvalido, match=erro):
            avatar.salvar("Lucas", {}, q)
        assert avatar.avatares() == []

    @pytest.mark.parametrize("nome", ["", "   ", "a" * 41, "../x", "<b>"])
    def test_nomes_que_nao_servem(self, nome):
        with pytest.raises(avatar.AvatarInvalido):
            avatar.salvar(nome, {}, _quadros())

    def test_apelido_esquisito_nao_sai_da_pasta(self):
        for slug in ("../etc", "a/b", "", "A"):
            with pytest.raises(avatar.AvatarInvalido):
                avatar.ler(slug)


# ── pela foto, com o Gemini ──────────────────────────────────────────────


def _foto() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (1600, 1200), (200, 150, 120)).save(buf, "JPEG")
    return buf.getvalue()


class TestPelaFoto:
    def test_com_a_ia_falsa_vem_o_padrao(self):
        r = avatar.escolher_partes(_foto())
        assert r["por"] == "falsa"
        assert r["escolhas"] == avatar.escolhas_validas({})

    def test_o_pedido_e_a_resposta(self, monkeypatch):
        monkeypatch.delenv(ia.VARIAVEL_FALSA, raising=False)
        monkeypatch.setenv(ia.VARIAVEL_DA_CHAVE, "AIzaSyTESTE-chave-de-mentira-123456")
        pedidos = []
        resposta = {"cabelo": "black-power", "barba": "cavanhaque", "oculos": "redondos",
                    "acessorio": "nenhum", "roupa": "camisa", "cor_pele": "#8a5636",
                    "cor_cabelo": "#1f1611", "cor_barba": "", "cor_olho": "#5a3a22",
                    "cor_roupa": "azul", "descricao": "um homem de óculos redondos"}

        def responder(pedido: httpx.Request) -> httpx.Response:
            pedidos.append(json.loads(pedido.content))
            return httpx.Response(200, json={"candidates": [{"content": {"parts": [
                {"text": json.dumps(resposta)}]}, "finishReason": "STOP"}]})

        r = avatar.escolher_partes(_foto(), transporte=httpx.MockTransport(responder))
        e = r["escolhas"]
        # "black-power" não existe no catálogo (o id é "afro"): vira o padrão
        assert e["cabelo"] == avatar.catalogo()["padrao"]["cabelo"]
        assert (e["barba"], e["oculos"], e["roupa"]) == ("cavanhaque", "redondos", "camisa")
        assert e["cores"]["pele"] == "#8a5636" and e["cores"]["barba"] == ""
        assert e["cores"]["roupa"] == avatar.catalogo()["padrao"]["cores"]["roupa"]
        assert r["descricao"] == "um homem de óculos redondos"
        partes = pedidos[0]["contents"][0]["parts"]
        foto = Image.open(io.BytesIO(base64.b64decode(partes[0]["inlineData"]["data"])))
        assert max(foto.size) == avatar.FOTO_LADO                # a foto vai reduzida
        assert '"topete"' in partes[1]["text"] and "nenhum" in partes[1]["text"]

    def test_foto_que_nao_e_imagem(self):
        with pytest.raises(avatar.AvatarInvalido):
            avatar.escolher_partes(b"isso nao e uma foto")


# ── a fala: a boca pelas sílabas ─────────────────────────────────────────


class TestAFala:
    def test_os_picos_como_o_scipy(self):
        # um platô vira o meio dele; dois picos perto ficam com o mais alto; um morrinho sem
        # proeminência sai
        env = np.array([0, .5, .5, .5, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, .9, .3, .95, .2,
                        .21, .2, 0], float)
        assert avatar._picos(env, 0.2, 0.07, 1).tolist() == [2, 17, 19]
        assert avatar._picos(env, 0.2, 0.07, 3).tolist() == [2, 19]
        assert avatar._picos(env, 0.6, 0.07, 1).tolist() == [17, 19]

    def test_uma_boca_por_silaba(self, tmp_path):
        x, taxa = _ler_wav(_silabas(tmp_path / "f.wav", n=12))
        picos, _env, _passo = avatar.silabas(x, taxa)
        assert len(picos) == 12
        fps = 30
        bocas = avatar.bocas_por_quadro(x, taxa, fps, round(len(x) / taxa * fps))
        aberturas = sum(1 for i, b in enumerate(bocas) if b != "fechada"
                        and (i == 0 or bocas[i - 1] == "fechada"))
        assert aberturas == 12
        for p in picos:                         # abre pela meia, um quadro antes do pico
            q = round(p * fps)
            assert bocas[q - 1] == "meia" and bocas[q - 2] == "fechada"
        assert bocas[:10] == ["fechada"] * 10   # o silêncio do começo
        assert bocas[-20:] == ["fechada"] * 20  # e o do fim

    def test_a_silaba_fraca_para_na_meia(self, tmp_path):
        x, taxa = _ler_wav(_silabas(tmp_path / "f.wav", n=9, fracas=(4,)))
        picos, _env, _passo = avatar.silabas(x, taxa)
        bocas = avatar.bocas_por_quadro(x, taxa, 30, round(len(x) / taxa * 30))
        trecho = lambda p: bocas[round(p * 30) - 1:round(p * 30) + 3]   # noqa: E731
        assert "aberta" not in trecho(picos[4])
        assert "aberta" in trecho(picos[3]) and "aberta" in trecho(picos[5])

    def test_sem_fala_fica_fechada(self):
        assert avatar.bocas_por_quadro(np.zeros(16_000), 16_000, 30, 30) == ["fechada"] * 30


# ── a pose de cada frase ─────────────────────────────────────────────────


class TestAPose:
    @pytest.mark.parametrize("texto, pose", [
        ("Você já reparou nisso?", "pensando"),
        ("Isso é pra você.", "apontando_voce"),
        ("Eu sinceramente não sabia.", "mao_no_peito"),
        ("São 3 passos!", "apontando_cima"),
        ("Olha aqui na tela.", "apontando_lado"),
        ("Pronto, funciona.", "joinha"),
        ("Calma, sem pressa.", "cafe"),
        ("Simples assim.", "bracos_cruzados"),
        ("Hahaha, que coisa.", "rindo"),
        ("Nossa, incrível.", "surpreso"),
    ])
    def test_as_regras(self, texto, pose):
        assert avatar.pose_da_fala(texto, "neutro") == pose

    def test_sem_regra_alterna_e_comeca_no_neutro(self):
        assert avatar.pose_da_fala("O céu é azul.") == "neutro"
        assert avatar.pose_da_fala("O céu é azul.", "neutro") == "explicando"
        assert avatar.pose_da_fala("O céu é azul.", "explicando") == "neutro"

    def test_as_frases_da_legenda(self):
        def bloco(*palavras):
            ws = [Palavra(t, a, b) for t, a, b in palavras]
            return Bloco(ws, ws[0].inicio, ws[-1].fim)

        blocos = [bloco(("O", 0.2, 0.4), ("céu", 0.4, 0.8)),
                  bloco(("é", 0.8, 1.0), ("azul.", 1.0, 1.6)),
                  bloco(("Você", 2.0, 2.4), ("sabia", 2.4, 2.9), ("disso?", 2.9, 3.6)),
                  bloco(("Ok.", 3.8, 4.0)),                # curta demais: fica com a anterior
                  bloco(("Olha", 5.2, 5.5), ("aqui", 5.5, 5.9), ("embaixo.", 5.9, 6.8))]
        poses = avatar.poses_das_falas(blocos)
        assert [p for *_, p in poses] == ["neutro", "pensando", "apontando_lado"]
        assert poses[0][:2] == (0.2, 2.0)                       # vale até a próxima frase
        assert poses[1][:2] == (2.0, 5.2)
        assert poses[2][:2] == (5.2, 6.8)

    def test_a_frase_comprida_troca_na_virgula(self):
        # a de um vídeo do dono: 6 s numa pose só, antes
        texto = ["Você", "já", "perdeu", "horas", "editando", "seus", "vídeos,", "cortando",
                 "silêncios,", "criando", "legendas,", "efeitos,", "animações", "e", "tudo",
                 "mais?"]
        ws = [Palavra(t, 0.3 * i, 0.3 * i + 0.28) for i, t in enumerate(texto)]
        poses = avatar.poses_das_falas([Bloco(ws, ws[0].inicio, ws[-1].fim)])
        assert len(poses) == 2                   # "Você… vídeos," e "cortando… mais?"
        assert poses[0][2] == "apontando_voce" and poses[-1][2] == "pensando"
        assert all(b - a >= avatar.FRASE_MINIMA_S for a, b, _ in poses)


# ── a camada da montagem ─────────────────────────────────────────────────


def _camada(poses, bocas, fps=10.0):
    quadros = {(p, b): _quadro(p, b) for p in avatar.poses() for b in avatar.bocas()}
    return montagem.CamadaDeAvatar(quadros, poses, bocas, fps)


class TestACamada:
    def test_recorta_e_mede_simetrico(self):
        c = _camada([(0.0, 5.0, "neutro")], ["fechada"] * 50)
        assert (c.largura, c.altura) == (520, 600)               # a caixa do desenho
        # medida com o espelho: virar não muda o lugar dele na tela
        assert c.pessoa.x0 == pytest.approx(1 - c.pessoa.x1, abs=0.01)

    def test_pose_boca_espelho_e_pulinho(self):
        poses = [(0.5, 2.0, "neutro"), (2.0, 4.0, "joinha")]
        bocas = ["fechada"] * 10 + ["meia", "aberta", "aberta", "meia"] + ["fechada"] * 26
        c = _camada(poses, bocas)
        boca = lambda q: tuple(q[330 - 150 + 30, 420 - 300 + 30, :3])    # noqa: E731
        cor = lambda q: tuple(q[500, 50, :3])                             # noqa: E731
        assert boca(c.quadro_em(0.0)) == COR_DA_BOCA["fechada"]          # antes da 1ª frase
        assert boca(c.quadro_em(1.15)) == COR_DA_BOCA["aberta"]
        assert boca(c.quadro_em(1.0)) == COR_DA_BOCA["meia"]
        assert cor(c.quadro_em(1.5)) == tuple(_quadro("neutro", "fechada")[650, 350, :3])
        assert cor(c.quadro_em(3.0)) == tuple(_quadro("joinha", "fechada")[650, 350, :3])
        # o braço (amarelo) fica à direita; espelhado, à esquerda
        amarelo = lambda q, x: tuple(q[160, x, :3]) == (250, 200, 0)      # noqa: E731
        normal, virado = c.quadro_em(3.0), c.quadro_em(3.0, direita=True)
        assert amarelo(normal, 500) and not amarelo(normal, 10)
        assert amarelo(virado, 10) and not amarelo(virado, 500)
        # o pulinho: logo depois da troca, menor e com os pés no chão
        pulo = c.quadro_em(2.02)
        assert pulo[:, :, 3].any(axis=1).nonzero()[0][0] > 5      # a cabeça desceu
        assert pulo[-1, :, 3].any()                                # a base no lugar
        assert c.pose_em(0.0) == ("neutro", None)                  # a primeira não pula
        assert c.pose_em(2.5)[1] == pytest.approx(0.5)

    def test_do_avatar_salvo(self):
        _salvar()
        c = montagem.CamadaDeAvatar.do_avatar("lucas-teles", [(0.0, 1.0, "cafe")], ["aberta"], 30)
        assert c.quadro_em(0.0)[200, 150, :3].tolist() == list(COR_DA_BOCA["aberta"])

    def test_no_video_a_boca_mexe_e_ele_vira_do_lado_direito(self, tmp_path):
        import av

        _salvar()
        fundo = _video_preto(tmp_path / "preto.mp4", segundos=4.0)
        fala = _silabas(tmp_path / "fala.wav", n=14)
        m = montagem.Montagem(fundo, avatar="lucas-teles", audio=fala, formato="horizontal")
        r = render.editar(None, tmp_path / "s.mp4", OpcoesDeEdicao(mover=False),
                          saida.OpcoesDeSaida(), montagem=m)
        info = ler_info(r.video)
        assert (info["largura"], info["altura"]) == (640, 360)
        abertas, virado, quadros = 0, 0, 0
        with av.open(str(r.video)) as cont:
            for fr in cont.decode(video=0):
                q = fr.to_ndarray(format="rgb24").astype(int)[:300]       # sem a legenda
                vermelho = (q[..., 0] > 180) & (q[..., 1] < 80) & (q[..., 2] < 80)
                abertas += int(vermelho.sum() > 20)
                amarelo = (q[..., 0] > 200) & (q[..., 1] > 150) & (q[..., 2] < 80)
                desenho = q.sum(-1) > 90                   # tudo o que não é o fundo preto
                if amarelo.any():
                    quadros += 1
                    virado += int(np.nonzero(amarelo)[1].mean() < np.nonzero(desenho)[1].mean())
        assert abertas >= 5, "a boca não abriu nenhuma vez"
        # deitado, a casa é embaixo à direita: ele vira para o meio (o braço à esquerda)
        assert quadros > 30 and virado == quadros


def _video_preto(caminho: Path, *, segundos: float, lado=(640, 360)) -> Path:
    from fractions import Fraction

    import av

    with av.open(str(caminho), "w") as cont:
        v = cont.add_stream("libx264", rate=Fraction(30))
        v.width, v.height, v.pix_fmt = *lado, "yuv420p"
        preto = np.zeros((lado[1], lado[0], 3), np.uint8)
        for _ in range(round(segundos * 30)):
            for pacote in v.encode(av.VideoFrame.from_ndarray(preto, format="rgb24")):
                cont.mux(pacote)
        for pacote in v.encode():
            cont.mux(pacote)
    return caminho


# ── a API e o terminal ───────────────────────────────────────────────────


PORTA, TOKEN = 8898, "token-de-teste"
CABECA = {"X-Editor-Token": TOKEN}


@pytest.fixture
def cliente(tmp_path):
    app = servidor.criar_app(TOKEN, porta=PORTA, pasta_saida=tmp_path / "saida")
    with TestClient(app, base_url=f"http://127.0.0.1:{PORTA}") as c:
        yield c


class TestAAPI:
    def test_criar_ver_baixar_e_apagar(self, cliente):
        assert cliente.get("/api/avatares", headers=CABECA).json() == {"avatares": []}
        arquivos = [("quadros", (n, d, "image/png")) for n, d in _quadros().items()]
        r = cliente.post("/api/avatares", headers=CABECA, files=arquivos,
                         data={"nome": "Lucas", "escolhas": json.dumps({"cabelo": "afro"})})
        assert r.status_code == 200, r.text
        assert r.json()["avatar"]["escolhas"]["cabelo"] == "afro"
        assert [a["apelido"] for a in r.json()["avatares"]] == ["lucas"]
        q = cliente.get("/api/avatares/lucas/quadros/neutro_meia.png", headers=CABECA)
        assert q.status_code == 200 and q.headers["content-type"] == "image/png"
        z = cliente.get("/api/avatares/lucas/pacote.zip", headers=CABECA)
        assert "avatar-lucas.zip" in z.headers["content-disposition"]
        assert len(zipfile.ZipFile(io.BytesIO(z.content)).namelist()) == 39
        assert cliente.get("/api/avatares/lucas", headers=CABECA).json()["nome"] == "Lucas"
        assert cliente.get("/api/avatares/lucas/quadros/../avatar.json",
                           headers=CABECA).status_code == 404
        assert cliente.delete("/api/avatares/lucas", headers=CABECA).json() == {"avatares": []}
        assert cliente.get("/api/avatares/lucas", headers=CABECA).status_code == 404

    def test_sem_token_nao_entra(self, cliente):
        assert cliente.get("/api/avatares").status_code == 401

    def test_quadros_faltando(self, cliente):
        arquivos = [("quadros", (n, d, "image/png")) for n, d in list(_quadros().items())[:5]]
        r = cliente.post("/api/avatares", headers=CABECA, files=arquivos, data={"nome": "Lucas"})
        assert r.status_code == 422 and "Faltam" in r.json()["detail"]

    def test_partes_pela_foto(self, cliente):
        r = cliente.post("/api/avatares/partes", headers=CABECA,
                         files={"foto": ("eu.jpg", _foto(), "image/jpeg")})
        assert r.status_code == 200 and r.json()["por"] == "falsa"

    def test_a_montagem_com_o_avatar(self, cliente, tmp_path):
        _salvar()
        fundo = fazer_video(tmp_path / "tela.mp4", largura=320, altura=180, segundos=2.0)
        with open(fundo, "rb") as f:
            vid = cliente.post("/api/videos", headers=CABECA,
                               files={"arquivo": ("tela.mp4", f, "video/mp4")}).json()["id"]
        pedido = {"montagem": {"fundo_id": vid, "avatar": "nao-existe", "recorte": "modnet",
                               "formato": "fundo", "fala": "fundo"}}
        r = cliente.post("/api/tarefas", headers=CABECA, json=pedido)
        assert r.status_code == 422 and "não existe" in r.json()["detail"]
        pedido["montagem"]["avatar"] = "lucas-teles"
        r = cliente.post("/api/tarefas", headers=CABECA, json={**pedido, "previa": 1})
        assert r.status_code == 200, r.text


class TestOTerminal:
    def test_avatar_que_nao_existe(self, tmp_path, capsys):
        from editor import cli

        fundo = fazer_video(tmp_path / "tela.mp4", largura=320, altura=180, segundos=1.0)
        assert cli.main(["--fundo", str(fundo), "--avatar", "Ninguém"]) != 0
        assert "não achei o avatar Ninguém" in capsys.readouterr().err

    def test_avatar_pelo_nome(self, tmp_path):
        from editor import cli

        _salvar()
        fundo = fazer_video(tmp_path / "tela.mp4", largura=320, altura=180, segundos=2.0)
        m, erro = cli._montagem(cli.argumentos().parse_args(
            ["--fundo", str(fundo), "--avatar", "Lucas Teles"]))
        assert erro == "" and m.avatar == "lucas-teles"
