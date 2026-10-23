"""O que você falou: a legenda de um vídeo gravado pega a grafia do texto colado, só onde
ele bate com o que o Whisper ouviu."""
from __future__ import annotations

from itertools import pairwise

import pytest

from editor import presets, render, transcricao
from editor.opcoes import OpcoesDeEdicao
from editor.transcricao import Palavra


def ouvidas(frase: str, inicio: float = 0.0, passo: float = 0.4) -> list[Palavra]:
    """As palavras de ``frase`` como o Whisper devolve: uma a cada ``passo`` segundos."""
    return [Palavra(w, round(inicio + k * passo, 3), round(inicio + k * passo + 0.3, 3), 0.9)
            for k, w in enumerate(frase.split())]


def textos(palavras: list[Palavra]) -> str:
    return " ".join(p.texto for p in palavras)


class TestAGrafia:
    def test_a_gravacao_de_verdade(self):
        # O que o Whisper ouviu numa gravação de 12/10 e o texto que o dono colou.
        fala = ouvidas("Foi pensando nisso que eu desenvolvia Edita I, uma ferramenta open source "
                       "que reúne edição automática de vídeos, síntese de voz e geração de "
                       "tambineios em um só lugar. Nela você também pode usar os meus processos "
                       "de edição.")
        texto = ("Foi pensando nisso que eu desenvolvi o **Editai**. [pausa]\n\nUma ferramenta "
                 "open source que reúne edição automática de vídeo, síntese de voz e geração de "
                 "thumbnails em um só lugar.\n\nNela você também pode usar meus presets de edição")
        assert textos(transcricao.grafia_do_texto(fala, texto)) == (
            "Foi pensando nisso que eu desenvolvi o Editai. Uma ferramenta open source que reúne "
            "edição automática de vídeo, síntese de voz e geração de thumbnails em um só lugar. "
            "Nela você também pode usar os meus presets de edição")

    def test_a_palavra_que_bate_fica_com_a_grafia_e_os_tempos(self):
        fala = ouvidas("eu fiz o editaí ontem")
        g = transcricao.grafia_do_texto(fala, "Eu fiz o Editai ontem!")
        assert textos(g) == "Eu fiz o Editai ontem!"
        assert [(p.inicio, p.fim, p.prob) for p in g] == [(p.inicio, p.fim, p.prob) for p in fala]

    def test_o_que_foi_pulado_nao_entra_e_o_improviso_fica(self):
        fala = ouvidas("você já perdeu horas editando seus vídeos")
        g = transcricao.grafia_do_texto(fala, "Você já perdeu horas do seu dia editando vídeos?")
        assert textos(g) == "Você já perdeu horas editando seus vídeos?"

    def test_a_gravacao_que_acabou_antes_do_texto(self):
        # Sem o resto do texto empurrado para depois da fala, como faz o ajustar_ao_texto.
        fala = ouvidas("o link está no post")
        g = transcricao.grafia_do_texto(fala, "O link está no post. Testa e me conta o que achou!")
        assert textos(g) == "O link está no post."
        assert g[-1].fim == fala[-1].fim

    def test_palavra_trocada_de_verdade_fica_como_foi_dita(self):
        fala = ouvidas("é uma plataforma de graça para todo mundo")
        g = transcricao.grafia_do_texto(fala, "É uma ferramenta de graça para todo mundo.")
        assert textos(g) == "É uma plataforma de graça para todo mundo."

    def test_frase_inteira_diferente_e_improviso(self):
        fala = ouvidas("então abre aí o editor e testa com qualquer vídeo que você tiver")
        texto = "Então abre o editor e testa um vídeo seu agora mesmo sem medo algum hoje."
        g = transcricao.grafia_do_texto(fala, texto)
        assert "você" in textos(g) and "tiver" in textos(g)        # o improviso continua lá

    def test_um_trecho_trocado_divide_o_tempo_das_ouvidas(self):
        fala = ouvidas("foi pensando nisso que eu desenvolvia Edita I ontem à noite")
        texto = "foi pensando nisso que eu desenvolvi o Editai ontem à noite"
        g = transcricao.grafia_do_texto(fala, texto)
        assert textos(g) == texto
        meio = g[5:8]
        assert meio[0].inicio == fala[5].inicio and meio[-1].fim == fala[7].fim
        assert all(a.fim <= b.inicio + 1e-9 for a, b in pairwise(meio))
        assert meio[2].fim - meio[2].inicio > meio[1].fim - meio[1].inicio   # pelas letras

    def test_numero_ouvido_casa_com_o_extenso(self):
        fala = ouvidas("custa 3.500 reais")
        g = transcricao.grafia_do_texto(fala, "Custa três mil e quinhentos reais.")
        assert textos(g) == "Custa três mil e quinhentos reais."
        assert g[1].inicio == fala[1].inicio and g[4].fim == fala[1].fim

    def test_outro_texto_nao_mexe(self):
        fala = ouvidas("uma coisa completamente diferente aqui")
        assert transcricao.grafia_do_texto(fala, "nada a ver com isso, sério mesmo") == fala

    def test_texto_vazio_ou_so_notas(self):
        fala = ouvidas("oi tudo bem")
        assert transcricao.grafia_do_texto(fala, "") == fala
        assert transcricao.grafia_do_texto(fala, "[pausa] 🚀 **") == fala
        assert transcricao.grafia_do_texto([], "Oi, tudo bem?") == []

    def test_o_que_nao_se_fala_sai_do_texto(self):
        fala = ouvidas("me conta o que achou")
        g = transcricao.grafia_do_texto(fala, "**Me conta** o que achou! 🚀 [sorrindo]")
        assert textos(g) == "Me conta o que achou!"


class TestNaEdicao:
    def test_o_limite_do_texto(self):
        assert OpcoesDeEdicao(texto_falado="a" * 20_000).problemas() == []
        assert "20.000 letras" in " ".join(OpcoesDeEdicao(texto_falado="a" * 20_001).problemas())

    def test_o_tema_tem_limite_e_fica_fora_dos_presets(self):
        """O tema do passo 1 é de um vídeo só, como o texto falado."""
        assert OpcoesDeEdicao(tema="a" * 200).problemas() == []
        assert "200 letras" in " ".join(OpcoesDeEdicao(tema="a" * 201).problemas())
        base = presets.PRESETS["vlog"]
        p = presets.salvar({"titulo": "Com tema", "frase": "", "edicao": {
            **base.edicao, "tema": "o céu azul"}, "saida": dict(base.saida),
            "thumb": {"modelo": "pergunta", "cor": "roxo"}})
        assert "tema" not in p.edicao and p.opcoes().tema == ""

    def test_o_render_usa_o_texto(self, tmp_path):
        fala = ouvidas("eu fiz o editaí")
        e = OpcoesDeEdicao(texto_falado="Eu fiz o Editai.")
        assert textos(render._com_a_grafia(fala, tmp_path / "video.mp4", e)) == "Eu fiz o Editai."
        assert render._com_a_grafia(fala, tmp_path / "video.mp4", OpcoesDeEdicao()) == fala

    def test_o_roteiro_da_narracao_ganha_do_texto(self, tmp_path):
        # A narração sintetizada leu o roteiro inteiro: vale ele, não o campo do passo 3.
        (tmp_path / "narracao.roteiro.txt").write_text("O PEGI deu dezoito anos!", encoding="utf-8")
        fala = ouvidas("o Peggy deu 18 anos")
        e = OpcoesDeEdicao(texto_falado="Outra coisa qualquer.")
        assert textos(render._com_a_grafia(fala, tmp_path / "narracao.wav", e)) == (
            "O PEGI deu dezoito anos!")

    def test_o_texto_nao_entra_no_preset(self):
        base = presets.PRESETS["vlog"]
        p = presets.salvar({"titulo": "Com texto", "frase": "", "edicao": {
            **base.edicao, "texto_falado": "Eu fiz o Editai."}, "saida": dict(base.saida),
            "thumb": {"modelo": "pergunta", "cor": "roxo"}})
        assert "texto_falado" not in p.edicao and p.opcoes().texto_falado == ""


class TestNoTerminal:
    @pytest.fixture
    def rodar(self, monkeypatch, tmp_path):
        from editor import cli

        visto = {}

        def falso(entrada, destino, edicao, saida, **kw):
            visto.update(edicao=edicao)
            raise SystemExit(0)

        monkeypatch.setattr(render, "editar", falso)
        video = tmp_path / "eu.mp4"
        video.write_bytes(b"x")

        def rodar(*flags: str):
            try:
                codigo = cli.main([str(video), *flags])
            except SystemExit as saida:
                codigo = saida.code
            return codigo, visto.get("edicao")

        return rodar

    def test_o_arquivo_vira_o_texto(self, rodar, tmp_path):
        arquivo = tmp_path / "fala.txt"
        arquivo.write_text("Eu fiz o Editai.", encoding="utf-8")
        _codigo, edicao = rodar("--texto-falado", str(arquivo))
        assert edicao.texto_falado == "Eu fiz o Editai."

    def test_arquivo_que_nao_existe(self, rodar, tmp_path, capsys):
        codigo, edicao = rodar("--texto-falado", str(tmp_path / "nada.txt"))
        assert (codigo, edicao) == (2, None)
        assert "não existe" in capsys.readouterr().err
