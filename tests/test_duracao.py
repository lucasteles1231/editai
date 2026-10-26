"""
A duração escolhida (editor/duracao.py): as escolhas, o limite das plataformas, as frases que
saem das palavras, a escolha pela IA (com o Gemini imitado), o corte no fim sem ela e o vídeo
de ponta a ponta encurtando para o alvo.
"""
from __future__ import annotations

import json
from itertools import pairwise

import httpx
import pytest

from editor import cli, cortes, duracao, ia, render, saida, transcricao
from editor.opcoes import OpcoesDeEdicao
from editor.transcricao import Palavra
from tests.conftest import fazer_video, ler_info


def _falas(segundos: float = 30.0) -> tuple[list[Palavra], cortes.Linha]:
    """As palavras da transcrição falsa (frases com ponto e pausa de 0,9 s), sem cortes."""
    return transcricao._falso(segundos), cortes.Linha([cortes.Trecho(0.0, segundos)])


class TestAsEscolhas:
    def test_ler(self):
        assert duracao.ler("auto") == "auto" and duracao.ler(None) == "auto"
        assert duracao.ler("tudo") == "tudo" and duracao.ler(" Tudo ") == "tudo"
        assert duracao.ler("30") == 30.0 and duracao.ler("45s") == 45.0
        assert duracao.ler(90) == 90.0
        for ruim in ("abc", "2", "99999"):
            with pytest.raises(duracao.DuracaoInvalida):
                duracao.ler(ruim)

    def test_o_menor_limite_das_plataformas(self):
        assert duracao.limite_das(["youtube"]) is None
        assert duracao.limite_das([]) is None
        assert duracao.limite_das(["tiktok"]) == 600
        assert duracao.limite_das(["youtube", "shorts", "tiktok"]) == 180

    def test_o_alvo(self):
        assert duracao.alvo("tudo", 180, 999) is None
        assert duracao.alvo("auto", 180, 170) is None            # cabe: nada sai
        assert duracao.alvo("auto", None, 999) is None           # sem limite
        a = duracao.alvo("auto", 180, 300)
        assert a.segundos == pytest.approx(171) and a.maximo == 180
        assert duracao.alvo("30", None, 34) is None              # dentro da folga
        a = duracao.alvo("30", None, 60)
        assert (a.segundos, a.minimo, a.maximo) == pytest.approx((30, 25.5, 34.5))

    def test_a_opcao_de_edicao_confere(self):
        assert not OpcoesDeEdicao(duracao="45", limite_da_plataforma=180).problemas()
        assert any("duração" in p for p in OpcoesDeEdicao(duracao="já").problemas())
        assert any("limite" in p for p in OpcoesDeEdicao(limite_da_plataforma=1).problemas())

    def test_o_terminal_recusa_uma_duracao_que_nao_existe(self, capsys):
        assert cli.main(["--duracao", "rapido", "--tema", "o céu"]) == 2
        assert "duração" in capsys.readouterr().err


class TestAsFrases:
    def test_saem_das_palavras_e_cortam_no_meio_da_pausa(self):
        palavras, linha = _falas(30.0)
        lista = duracao.frases(palavras, linha, 30.0)
        assert len(lista) >= 6
        assert lista[0].texto == "Hoje eu vou mostrar como funciona o editor."
        assert lista[1].texto.startswith("Ele corta as pausas")
        for a, b in pairwise(lista):
            assert a.corte_fim == b.corte_ini
            assert a.fim < a.corte_fim < b.ini            # no meio da pausa
        assert lista[0].corte_ini == 0 and lista[-1].corte_fim == 30.0
        assert sum(f.segundos for f in lista) == pytest.approx(30.0, abs=0.05)

    def test_sem_pontuacao_a_pausa_fecha_a_frase(self):
        palavras = [Palavra("uma", 0.0, 0.3), Palavra("frase", 0.4, 0.7),
                    Palavra("outra", 1.6, 1.9), Palavra("aqui", 2.0, 2.3)]
        lista = duracao.frases(palavras, cortes.Linha([cortes.Trecho(0, 2.5)]), 2.5)
        assert [f.texto for f in lista] == ["uma frase", "outra aqui"]

    def test_o_cruzamento_com_os_silencios(self):
        trechos = [cortes.Trecho(0, 5), cortes.Trecho(6, 10)]
        assert cortes.cruzar(trechos, [(2, 7)]) == [cortes.Trecho(2, 5), cortes.Trecho(6, 7)]
        assert cortes.cruzar(trechos, [(5.2, 5.8)]) == []


class TestAEscolha:
    def test_o_auto_nao_corta_o_que_cabe(self):
        palavras, linha = _falas(30.0)
        sel = duracao.escolher(palavras, linha, 30.0, escolha="auto", limite=180)
        assert sel.manter is None and not sel.fora and sel.por == ""
        assert sel.depois == pytest.approx(30.0)

    def test_com_a_ia_falsa_corta_no_fim(self):
        palavras, linha = _falas(30.0)
        sel = duracao.escolher(palavras, linha, 30.0, escolha="12")
        assert sel.por == "falsa" and sel.manter and sel.fora
        assert sel.depois <= 12 * 1.15
        assert sel.fora[0].ini > sel.manter[-1][1] - 0.5          # o que sai é o fim
        assert json.dumps(sel.para_json())

    def test_sem_ia_corta_no_fim_e_avisa(self, monkeypatch):
        monkeypatch.delenv(ia.VARIAVEL_FALSA, raising=False)
        palavras, linha = _falas(30.0)
        sel = duracao.escolher(palavras, linha, 30.0, escolha="12")
        assert sel.por == "fim" and "Sem IA" in sel.aviso
        assert sel.manter[0][0] == 0.0

    def test_uma_frase_so_nao_corta(self):
        palavras = [Palavra(f"p{k}", k * 0.4, k * 0.4 + 0.3) for k in range(100)]
        linha = cortes.Linha([cortes.Trecho(0, 40)])
        sel = duracao.escolher(palavras, linha, 40.0, escolha="15")
        assert sel.manter is None and "uma frase só" in sel.aviso


class TestOPrimeiroCorteDeVerdade:
    """O corte de 3 min para 45 s de 25/10/2026: o "Da" da frase seguinte na legenda e as
    frases que retomavam outra que tinha saído."""

    def test_a_primeira_palavra_da_frase_seguinte_nao_entra_na_legenda(self):
        # o Whisper põe o "Da" (da frase que sai) 50 ms antes do fim do "todo."
        palavras = [Palavra("o", 0.0, 0.3), Palavra("tempo", 0.35, 0.7),
                    Palavra("todo.", 0.75, 1.05), Palavra("Da", 1.0, 1.4),
                    Palavra("próxima", 1.45, 1.9), Palavra("vez.", 1.95, 2.3)]
        linha = cortes.Linha([cortes.Trecho(0.0, 2.5)])
        lista = duracao.frases(palavras, linha, 2.5)
        assert [f.texto for f in lista] == ["o tempo todo.", "Da próxima vez."]
        sel = duracao.Selecao("1", fora=[lista[1]],
                              manter=[(lista[0].corte_ini, lista[0].corte_fim)])
        nova = cortes.Linha(cortes.cruzar(linha.trechos, sel.manter))
        assert "Da" in [w.texto for w in nova.palavras(palavras)]       # o defeito de antes
        assert "Da" not in [w.texto for w in nova.palavras(sel.sem_as_de_fora(palavras))]

    def test_a_frase_que_retoma_a_anterior_so_fica_com_ela(self):
        textos = ["Isso começa no céu.", "Os satélites mandam sinais.",
                  "Esses sinais têm a hora.", "Por isso o celular mede a distância.",
                  "No fim, tudo se encaixa."]
        lista = [duracao.Frase(k, t, k * 4.0, k * 4.0 + 3.5, segundos=4.0)
                 for k, t in enumerate(textos)]
        assert duracao.soltas(lista, [0, 2, 4]) == [(2, "esses")]     # a 0 pode retomar
        assert duracao.soltas(lista, [1, 2, 3]) == []
        a = duracao.Alvo(12, 10, 14)
        _ids, problemas = duracao.conferir({"manter": [0, 3, 4]}, lista, a)
        assert problemas == ['a frase 3 começa com "por isso" e depende da 2, que saiu: '
                             "mantenha as duas ou tire as duas"]
        assert not duracao._retoma("Essencial é o relógio.")          # "essa" não é "essencial"


class _Gemini:
    """O Gemini imitado: responde o que estiver na fila e guarda os pedidos."""

    def __init__(self, *respostas: dict):
        self.fila = list(respostas)
        self.pedidos: list[dict] = []

    def __call__(self, pedido: httpx.Request) -> httpx.Response:
        self.pedidos.append(json.loads(pedido.content))
        texto = json.dumps(self.fila.pop(0))
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": texto}]},
                                                         "finishReason": "STOP"}]})


@pytest.fixture
def gemini_de_verdade(monkeypatch):
    monkeypatch.delenv(ia.VARIAVEL_FALSA, raising=False)
    monkeypatch.setenv(ia.VARIAVEL_DA_CHAVE, "AIzaSyTESTE-chave-de-mentira-123456")


class TestAIA:
    def test_escolhe_as_frases_e_pode_comecar_mais_adiante(self, gemini_de_verdade):
        palavras, linha = _falas(30.0)
        # a 1 ("Ele corta...") depende da 0, que diz quem é "ele": a escolha começa na 2
        g = _Gemini({"manter": [2, 3, 4], "porque": "a apresentação saiu"})
        sel = duracao.escolher(palavras, linha, 30.0, escolha="12", tema="o editor",
                               transporte=httpx.MockTransport(g))
        lista = duracao.frases(palavras, linha, 30.0)
        assert sel.por == "gemini" and sel.pedidos == 1 and not sel.aviso
        # as três vizinhas viram um intervalo só, do meio da pausa ao meio da pausa
        assert sel.manter == [(lista[2].corte_ini, lista[4].corte_fim)]
        assert [f.k for f in sel.fora] == [0, 1, *range(5, len(lista))]
        texto = g.pedidos[0]["contents"][0]["parts"][-1]["text"]
        assert "O tema do vídeo: o editor" in texto and "- 0 (" in texto
        assert "entre 10 e 14 s" in texto

    def test_o_conserto_quando_passa_do_tempo(self, gemini_de_verdade):
        palavras, linha = _falas(30.0)
        g = _Gemini({"manter": [0, 1, 2, 3, 4, 5], "porque": "tudo"},
                    {"manter": [0, 1, 2], "porque": "o fim saiu"})
        sel = duracao.escolher(palavras, linha, 30.0, escolha="12",
                               transporte=httpx.MockTransport(g))
        assert sel.pedidos == 2 and sel.depois <= 12 * 1.15
        assert "A RESPOSTA ANTERIOR TEVE ESTES PROBLEMAS" in \
            g.pedidos[1]["contents"][0]["parts"][-1]["text"]

    def test_sem_conserto_que_sirva_apara_no_fim(self, gemini_de_verdade):
        palavras, linha = _falas(30.0)
        demais = {"manter": [0, 1, 2, 3, 4, 5], "porque": "tudo"}
        sel = duracao.escolher(palavras, linha, 30.0, escolha="12",
                               transporte=httpx.MockTransport(_Gemini(demais, demais)))
        assert sel.depois <= 12 * 1.15 and "passou do tempo" in sel.aviso


class TestDePontaAPonta:
    def test_o_video_encurta_para_o_alvo(self, tmp_path):
        entrada = fazer_video(tmp_path / "e.mp4", segundos=30.0)
        r = render.editar(entrada, tmp_path / "s.mp4", OpcoesDeEdicao(duracao="12"),
                          saida.OpcoesDeSaida())
        assert r.duracao_final <= 12 * 1.15 + 0.2
        assert r.selecao["fora"] and r.selecao["por"] == "falsa"
        assert ler_info(r.video)["duracao"] == pytest.approx(r.duracao_final, abs=0.15)
        plano = json.loads(r.plano.read_text(encoding="utf-8"))
        assert plano["selecao"]["fora"] == r.selecao["fora"]
        # a legenda só tem o que ficou
        ditas = " ".join(b["texto"] for b in plano["blocos"])
        assert r.selecao["fora"][-1]["texto"].split()[0] not in ditas.split()[-3:]

    def test_tudo_nao_tira_frase(self, tmp_path):
        entrada = fazer_video(tmp_path / "e.mp4", segundos=12.0)
        r = render.editar(entrada, tmp_path / "s.mp4", OpcoesDeEdicao(duracao="tudo"),
                          saida.OpcoesDeSaida())
        assert not r.selecao["fora"] and r.selecao["depois"] == pytest.approx(r.duracao_final)
