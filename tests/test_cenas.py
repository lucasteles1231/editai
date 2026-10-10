"""
A biblioteca de cenas: a matriz casada com os clipes, os blocos da fala, a escolha pelas
palavras (sem o Gemini), a trilha e o fundo feito das cenas.

Os clipes são de uma cor só, feitos pelo PyAV, para dar para saber qual cena aparece em
cada instante.
"""
from __future__ import annotations

import itertools
import json
from pathlib import Path

import av
import numpy as np
import pytest

from editor import cenas
from editor.cenas import Biblioteca, Cena
from editor.transcricao import Palavra


def _clipe(caminho: Path, cor=(200, 40, 40), segundos: float = 1.0, fps: int = 30) -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with av.open(str(caminho), "w") as c:
        v = c.add_stream("libx264", rate=fps, options={"crf": "18", "preset": "ultrafast"})
        v.width, v.height, v.pix_fmt = 160, 90, "yuv420p"
        q = np.empty((90, 160, 3), np.uint8)
        q[...] = cor
        for i in range(round(segundos * fps)):
            f = av.VideoFrame.from_ndarray(q, format="rgb24")
            f.pts = i
            for p in v.encode(f):
                c.mux(p)
        for p in v.encode():
            c.mux(p)
    return caminho


MATRIZ = [
    {"id": "t1-001", "arquivo": "public/cenas/t1-001.mp4",
     "descricao": "explosão de um carro na rodovia", "categorias": ["ação"], "energia": "alta"},
    {"id": "t1-002", "arquivo": "t1-002.mp4", "descricao": "praia ao pôr do sol",
     "categorias": "paisagem, calma", "energia": "baixa"},
    {"id": "t1-003", "arquivo": "T1-003.MP4", "descricao": "boate com luzes neon",
     "monetizacao": "cuidado"},
    {"id": "t1-004", "arquivo": "t1-004.mp4", "descricao": "cena proibida",
     "monetizacao": "evitar"},
    {"id": "t1-005", "arquivo": "falta.mp4", "descricao": "não veio na pasta"},
]


def _fala(texto: str, inicio: float = 0.0, passo: float = 0.4) -> list[Palavra]:
    """Uma palavra a cada ``passo`` segundos, cada uma durando 0,3 s."""
    return [Palavra(w, round(inicio + i * passo, 3), round(inicio + i * passo + 0.3, 3))
            for i, w in enumerate(texto.split())]


def _cena(ident: str, descricao: str, **extra) -> Cena:
    return Cena(ident, Path(f"{ident}.mp4"), descricao, duracao=extra.pop("duracao", 2.0),
                **extra)


class TestAMatriz:
    @pytest.fixture
    def clipes(self, tmp_path) -> list[Path]:
        pasta = tmp_path / "cenas"
        nomes = ["t1-001.mp4", "sub/t1-002.mp4", "t1-003.mp4", "t1-004.mp4", "sobra.mp4"]
        return [_clipe(pasta / n) for n in nomes]

    def test_casa_pelo_nome_e_deixa_de_fora_as_evitar(self, clipes):
        b = cenas.ler_matriz(json.dumps(MATRIZ), clipes)
        assert [c.id for c in b.cenas] == ["t1-001", "t1-002", "t1-003"]
        assert b.evitadas == 1
        assert b.sem_clipe == ["t1-005"]
        assert b.sem_descricao == ["sobra.mp4"]
        praia = b.por_id()["t1-002"]
        assert praia.categorias == ["paisagem", "calma"]       # texto com vírgulas também vale
        assert praia.energia == "baixa" and praia.monetizacao == "ok"
        assert praia.duracao == pytest.approx(1.0, abs=0.05)
        assert (praia.largura, praia.altura) == (160, 90)
        assert b.ficha() == {"cenas": 3, "duracao": pytest.approx(3.0, abs=0.1), "fotos": 0,
                             "evitadas": 1, "sem_clipe": ["t1-005"],
                             "sem_descricao": ["sobra.mp4"]}

    def test_aceita_a_lista_dentro_de_cenas(self, clipes):
        b = cenas.ler_matriz({"versao": 2, "cenas": MATRIZ}, clipes)
        assert len(b.cenas) == 3

    def test_a_linha_do_pedido(self, clipes):
        linha = cenas.ler_matriz(MATRIZ, clipes).por_id()["t1-001"].linha()
        assert linha.startswith("t1-001 | explosão de um carro na rodovia | categorias: ação")
        assert "energia: alta" in linha and linha.endswith("1.0 s")

    @pytest.mark.parametrize(("dados", "trecho"), [
        ("{não é json", "não é um JSON válido"),
        ("[]", "precisa ser uma lista"),
        ('{"cenas": {}}', "precisa ser uma lista"),
        ('[{"arquivo": "t1-001.mp4"}]', 'a cena 1 da matriz não tem "arquivo" e "descricao"'),
        ('[{"arquivo": "outro.mp4", "descricao": "x"}]', "nenhuma cena da matriz casou"),
    ])
    def test_matriz_invalida(self, clipes, dados, trecho):
        with pytest.raises(cenas.MatrizInvalida, match=trecho):
            cenas.ler_matriz(dados, clipes)

    def test_os_clipes_da_pasta(self, tmp_path):
        _clipe(tmp_path / "a.mp4")
        _clipe(tmp_path / "fundo" / "b.mov")
        (tmp_path / "cenas.json").write_text("[]", encoding="utf-8")
        (tmp_path / "._a.mp4").write_bytes(b"lixo do macOS")
        assert [p.name for p in cenas.clipes_da_pasta(tmp_path)] == ["a.mp4", "b.mov"]


class TestOsBlocos:
    def test_fecham_nas_frases_e_cobrem_o_video(self):
        palavras = _fala("A Rockstar não vai pegar leve no jogo novo. A ficha completa saiu "
                         "e sumiu logo depois. Fim.")
        blocos = cenas.blocos_da_fala(palavras, 9.0)
        assert [b.texto for b in blocos] == [
            "A Rockstar não vai pegar leve no jogo novo.",
            "A ficha completa saiu e sumiu logo depois. Fim."]       # o "Fim." curto junta
        assert blocos[0].inicio == 0.0 and blocos[-1].fim == 9.0
        assert blocos[1].inicio == palavras[9].inicio == blocos[0].fim
        assert (blocos[1].primeira, blocos[1].ultima) == (9, len(palavras) - 1)

    def test_nenhum_passa_de_6_s(self):
        palavras = _fala(" ".join(f"palavra{i}" for i in range(40)))     # 16 s sem ponto
        blocos = cenas.blocos_da_fala(palavras, 16.0)
        assert len(blocos) >= 3
        for b in blocos:
            fala = palavras[b.ultima].fim - palavras[b.primeira].inicio
            assert fala <= cenas.BLOCO_MAXIMO_S

    def test_uma_pausa_longa_fecha_o_bloco(self):
        palavras = (_fala("um dois três quatro cinco seis")
                    + _fala("sete oito nove dez onze doze", inicio=4.0))
        blocos = cenas.blocos_da_fala(palavras, 7.0)
        assert [b.texto for b in blocos] == ["um dois três quatro cinco seis",
                                             "sete oito nove dez onze doze"]
        assert blocos[1].inicio == 4.0

    def test_o_ultimo_curto_junta_com_o_anterior(self):
        palavras = _fala("um dois três quatro cinco seis") + _fala("sete oito", inicio=4.0)
        assert [b.texto for b in cenas.blocos_da_fala(palavras, 5.0)] == [
            "um dois três quatro cinco seis sete oito"]

    def test_sem_fala(self):
        assert [(b.inicio, b.fim) for b in cenas.blocos_da_fala([], 5.0)] == [(0.0, 5.0)]
        assert cenas.blocos_da_fala([], 0.0) == []

    @pytest.mark.parametrize(("duracao", "quantas"), [(1.0, 1), (2.2, 1), (4.3, 2), (5.0, 3)])
    def test_uma_cena_a_cada_2_s(self, duracao, quantas):
        assert cenas.cenas_por_bloco(cenas.BlocoDeFala(0.0, duracao, 0, 0, "")) == quantas


class TestAEscolhaPelasPalavras:
    BIBLIOTECA = Biblioteca([
        _cena("praia", "praia ao pôr do sol", energia="baixa"),
        _cena("explosao", "explosão de um carro na rodovia", energia="alta"),
        _cena("boate1", "boate com luzes", monetizacao="cuidado"),
        _cena("boate2", "boate lotada", monetizacao="cuidado"),
        _cena("boate3", "boate vazia", monetizacao="cuidado"),
        _cena("cidade", "cidade à noite", energia="media"),
        _cena("policia", "perseguição da polícia", energia="alta"),
    ])

    def _blocos(self, *textos: str) -> list[cenas.BlocoDeFala]:
        return [cenas.BlocoDeFala(2.0 * k, 2.0 * k + 2.0, 0, 0, t) for k, t in enumerate(textos)]

    def test_a_explosao_acha_a_cena_da_explosao(self):
        escolhas = cenas.escolher_por_palavras(
            self._blocos("tudo calmo na praia", "e o carro sofreu uma explosão"),
            self.BIBLIOTECA)
        assert escolhas[1] == ["explosao"]

    def test_o_plural_e_o_acento_casam(self):
        escolhas = cenas.escolher_por_palavras(self._blocos("tem várias praias", "as boates"),
                                               self.BIBLIOTECA)
        assert escolhas[0] == ["praia"] and escolhas[1][0].startswith("boate")

    def test_nao_repete_cena(self):
        escolhas = cenas.escolher_por_palavras(
            self._blocos("a praia", "outra praia", "mais praia", "praia de novo"),
            self.BIBLIOTECA)
        todas = [i for e in escolhas for i in e]
        assert len(todas) == len(set(todas)) == 4
        assert escolhas[0] == ["praia"]

    def test_cuidado_no_maximo_duas(self):
        escolhas = cenas.escolher_por_palavras(
            self._blocos("a boate", "outra boate", "mais boate"), self.BIBLIOTECA)
        cuidado = [i for e in escolhas for i in e if i.startswith("boate")]
        assert len(cuidado) == cenas.CUIDADO_MAXIMO

    def test_o_gancho_sem_casamento_pede_energia_alta(self):
        escolhas = cenas.escolher_por_palavras(self._blocos("olha só isso aqui"),
                                               self.BIBLIOTECA)
        assert self.BIBLIOTECA.por_id()[escolhas[0][0]].energia == "alta"

    def test_sem_casamento_roda_as_cenas_ok(self):
        escolhas = cenas.escolher_por_palavras(self._blocos(*["nada a ver"] * 6),
                                               self.BIBLIOTECA)
        assert all(e and not e[0].startswith("boate") for e in escolhas)
        # quatro cenas "ok": as quatro aparecem antes de alguma repetir
        assert {e[0] for e in escolhas[:4]} == {"praia", "explosao", "cidade", "policia"}


class TestATrilha:
    BIBLIOTECA = Biblioteca([_cena("a", "a", duracao=1.0), _cena("b", "b", duracao=2.0),
                             _cena("c", "c", duracao=2.0)])

    def test_cobre_o_video_sem_buraco(self):
        blocos = [cenas.BlocoDeFala(0.0, 3.0, 0, 0, ""), cenas.BlocoDeFala(3.0, 7.0, 1, 1, "")]
        cortes = cenas.montar_trilha(blocos, [["a"], ["b", "c"]], self.BIBLIOTECA)
        assert cortes[0].inicio == 0.0 and cortes[-1].fim == 7.0
        for antes, depois in itertools.pairwise(cortes):
            assert depois.inicio == antes.fim
        assert {c.cena.id for c in cortes if c.bloco == 0} == {"a"}       # a repete
        assert [c.cena.id for c in cortes if c.bloco == 1] == ["b", "c", "b"]
        # cada corte para um quadro antes do fim da cena
        assert all(c.fim - c.inicio <= c.cena.duracao - cenas.SOBRA_S + 1e-3 for c in cortes)

    def test_cena_que_nao_existe_vira_a_primeira(self):
        cortes = cenas.montar_trilha([cenas.BlocoDeFala(0.0, 0.8, 0, 0, "")], [["nenhuma"]],
                                     self.BIBLIOTECA)
        assert [c.cena.id for c in cortes] == ["a"]


class TestOFundoDeCenas:
    def test_cada_instante_mostra_a_cena_do_bloco(self, tmp_path):
        vermelho = _clipe(tmp_path / "vermelho.mp4", (220, 30, 30))
        azul = _clipe(tmp_path / "azul.mp4", (30, 30, 220))
        b = Biblioteca([Cena("vermelho", vermelho, "x", duracao=1.0, largura=160, altura=90),
                        Cena("azul", azul, "y", duracao=1.0, largura=160, altura=90)])
        blocos = [cenas.BlocoDeFala(0.0, 0.9, 0, 0, ""), cenas.BlocoDeFala(0.9, 1.8, 1, 1, "")]
        fundo = cenas.FundoDeCenas(cenas.montar_trilha(blocos, [["vermelho"], ["azul"]], b),
                                   (64, 36))
        assert fundo.corte_em(0.5).cena.id == "vermelho"
        assert fundo.corte_em(1.2).cena.id == "azul"
        q = fundo.em(0.5)
        assert q.shape == (36, 64, 3)
        assert q[..., 0].mean() > 150 and q[..., 2].mean() < 80
        q = fundo.em(1.2)
        assert q[..., 2].mean() > 150 and q[..., 0].mean() < 80

    def test_cobrir_corta_para_o_tamanho(self):
        q = np.zeros((100, 100, 3), np.uint8)
        assert cenas.cobrir(q, 160, 90).shape == (90, 160, 3)
        assert cenas.cobrir(q, 100, 100) is q


def _foto(caminho: Path, tamanho=(90, 160), cor=(40, 160, 60), girada: bool = False) -> Path:
    """Uma foto em pé; com ``girada``, gravada deitada e endireitada pelo EXIF, como o
    celular faz."""
    from PIL import Image

    caminho.parent.mkdir(parents=True, exist_ok=True)
    largura, altura = tamanho
    im = Image.new("RGB", (altura, largura) if girada else (largura, altura), cor)
    # uma faixa clara no alto da foto (depois de endireitada), para ver o lado
    if girada:
        im.paste((250, 250, 250), (0, 0, 20, largura))
        exif = im.getexif()
        exif[0x0112] = 6                            # girar 90° no sentido do relógio
        im.save(caminho, exif=exif.tobytes())
    else:
        im.paste((250, 250, 250), (0, 0, largura, 20))
        im.save(caminho)
    return caminho


class TestAsFotos:
    def test_entram_na_pasta_e_na_matriz(self, tmp_path):
        _clipe(tmp_path / "sala.mp4")
        foto = _foto(tmp_path / "fotos" / "cozinha.JPG", girada=True)
        assert [c.name for c in cenas.clipes_da_pasta(tmp_path)] == ["cozinha.JPG", "sala.mp4"]
        b = cenas.ler_matriz([{"arquivo": "fotos/cozinha.JPG", "descricao": "a cozinha"},
                              {"arquivo": "sala.mp4", "descricao": "a sala"}],
                             cenas.clipes_da_pasta(tmp_path))
        cozinha = b.por_id()["cozinha"]
        assert cozinha.imagem and cozinha.arquivo == foto
        assert cozinha.duracao == cenas.FOTO_S
        assert (cozinha.largura, cozinha.altura) == (90, 160)      # endireitada pelo EXIF
        assert b.ficha()["fotos"] == 1 and "foto" in cozinha.linha()

    def test_a_maioria_em_pe_decide(self, tmp_path):
        clipes = [_foto(tmp_path / f"{k}.jpg") for k in range(2)] + [_clipe(tmp_path / "d.mp4")]
        b = cenas.ler_matriz([{"arquivo": c.name, "descricao": "x"} for c in clipes], clipes)
        assert b.em_pe()

    def test_a_foto_mexe_devagar_e_fica_no_tamanho(self, tmp_path):
        foto = _foto(tmp_path / "quarto.jpg", tamanho=(180, 320))
        b = Biblioteca([Cena("quarto", foto, "x", duracao=cenas.FOTO_S, largura=180, altura=320,
                             tipo="imagem")])
        blocos = [cenas.BlocoDeFala(0.0, 3.0, 0, 0, "")]
        fundo = cenas.FundoDeCenas(cenas.montar_trilha(blocos, [["quarto"]], b), (90, 160))
        comeco, fim = fundo.em(0.05), fundo.em(2.9)
        assert comeco.shape == fim.shape == (160, 90, 3)
        assert np.abs(comeco.astype(int) - fim.astype(int)).mean() > 0.5     # mexeu
        assert comeco[:5].mean() > 200                       # a faixa clara continua no alto

    def test_foto_em_pe_num_quadro_deitado_entra_inteira(self, tmp_path):
        q = np.zeros((160, 90, 3), np.uint8)
        q[:, :] = (200, 30, 30)
        saida = cenas.ajustar(q, 320, 180)
        assert saida.shape == (180, 320, 3)
        # a foto inteira no meio, e dos lados o desfoque dela (vermelho também, mais escuro
        # nas bordas do desfoque), em vez de um corte que perderia metade
        meio = saida[:, 160 - 45: 160 + 45]
        assert meio[..., 0].mean() > 180
        parecido = np.zeros((90, 160, 3), np.uint8)
        assert cenas.ajustar(parecido, 160, 90) is parecido      # a mesma forma: nada muda


class TestOSomDasCenas:
    """Um vídeo de onde vem o som, escolhido como cena, entra no ponto da fala."""

    def _biblioteca(self, tmp_path):
        a = _clipe(tmp_path / "a.mp4", segundos=6.0)
        b = _clipe(tmp_path / "b.mp4", segundos=6.0)
        foto = _foto(tmp_path / "sala.jpg")
        return Biblioteca([Cena("a", a, "x", duracao=6.0), Cena("b", b, "y", duracao=6.0),
                           Cena("sala", foto, "z", duracao=cenas.FOTO_S, tipo="imagem")])

    def test_no_ponto_da_fala_e_de_quem_fala(self, tmp_path):
        from editor.cortes import Linha, Trecho

        bib = self._biblioteca(tmp_path)
        a, b, sala = bib.cenas
        # o som: "a" (aparado 0,4 s no começo) de 0 a 5 s; "b" de 5,3 a 10 s
        fontes = [(a.arquivo, 0.0, 0.4, 5.0), (b.arquivo, 5.3, 0.0, 4.7)]
        cortes = [cenas.Corte(0, 2, sala), cenas.Corte(2, 4, b), cenas.Corte(6, 8, a)]
        saida = cenas.sincronizar(cortes, fontes, Linha([Trecho(0.0, 10.0)]), bib)
        assert saida[0].cena is sala                           # a foto fica como está
        assert (saida[1].cena.id, saida[1].desde) == ("a", 2.4)   # quem fala é "a"
        assert (saida[2].cena.id, saida[2].desde) == ("b", pytest.approx(0.7))

    def test_o_corte_de_silencio_parte_a_cena(self, tmp_path):
        from editor.cortes import Linha, Trecho

        bib = self._biblioteca(tmp_path)
        a, _b, _ = bib.cenas
        fontes = [(a.arquivo, 0.0, 0.0, 5.0)]
        # de 3 a 5 s a pausa foi cortada: na saída, o 3 emenda no 5
        linha = Linha([Trecho(0.0, 3.0), Trecho(5.0, 10.0)])
        saida = cenas.sincronizar([cenas.Corte(2.0, 4.0, a)], fontes, linha, bib)
        assert [(c.inicio, c.fim, c.desde) for c in saida] == [(2.0, 3.0, 2.0), (3.0, 4.0, 0.0)]
        # o segundo pedaço caiu fora da fala de "a" (5 s em diante): fica como estava

    def test_sem_fonte_na_biblioteca_nada_muda(self, tmp_path):
        from editor.cortes import Linha, Trecho

        bib = self._biblioteca(tmp_path)
        cortes = [cenas.Corte(0, 2, bib.cenas[0])]
        assert cenas.sincronizar(cortes, [(tmp_path / "narracao.wav", 0, 0, 9)],
                                 Linha([Trecho(0.0, 9.0)]), bib) == cortes
