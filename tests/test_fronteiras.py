"""
O começo e o fim reais da fala (editor/fronteiras.py), com as armadilhas que o gabarito marcado
à mão mostrou: o "s" que só a faixa de cima vê, a cauda que some devagar, o respiro e o estalo
dentro da pausa, o ronco grave, a palavra que o Whisper põe dentro do silêncio, o portão de ruído
(zeros) e o trecho sem pausa nenhuma.
"""
from __future__ import annotations

import numpy as np
import pytest

from editor import fronteiras
from editor.transcricao import Palavra

TAXA = 48_000
DURACAO = 3.0
#: A régua dos testes: as bordas a até 15 ms do som.
PERTO = 0.015


def _tempo() -> np.ndarray:
    return np.arange(round(DURACAO * TAXA)) / TAXA


def _fundo(db: float = -70.0, semente: int = 1) -> np.ndarray:
    rng = np.random.default_rng(semente)
    return (rng.standard_normal(round(DURACAO * TAXA)) * 10 ** (db / 20)).astype(np.float64)


def _vogal(som: np.ndarray, ini: float, fim: float, amplitude: float = 0.3) -> None:
    """Uma vogal: 180 Hz e os harmônicos até 3,6 kHz, com rampas de 5 ms."""
    t = _tempo()
    trecho = (t >= ini) & (t < fim)
    tt = t[trecho] - ini
    onda = sum(np.sin(2 * np.pi * 180 * h * tt) / h for h in range(1, 21))
    rampa = np.minimum(1, np.minimum(tt, fim - ini - tt) / 0.005)
    som[trecho] += amplitude * 0.5 * onda * rampa


def _chiado(som: np.ndarray, ini: float, fim: float, amplitude: float,
            acima_hz: float = 4_000, semente: int = 2) -> None:
    """Um ruído filtrado: acima de 4 kHz é um "s"; de banda larga, um respiro."""
    t = _tempo()
    trecho = (t >= ini) & (t < fim)
    rng = np.random.default_rng(semente)
    ruido = rng.standard_normal(int(trecho.sum()))
    espectro = np.fft.rfft(ruido)
    espectro[np.fft.rfftfreq(len(ruido), 1 / TAXA) < acima_hz] = 0
    ruido = np.fft.irfft(espectro, len(ruido))
    som[trecho] += amplitude * ruido / max(float(np.std(ruido)), 1e-9)


def _duas_falas() -> np.ndarray:
    """A fala de 0,5 a 1,2 s, a pausa e a fala de 2,0 a 2,6 s, num fundo de −70 dB."""
    som = _fundo()
    _vogal(som, 0.5, 1.2)
    _vogal(som, 2.0, 2.6)
    return som


#: O Whisper: o fim cedo e o começo seguinte cedo também, como no gabarito.
CEDO_A = Palavra("antes", 0.5, 1.1)
CEDO_B = Palavra("depois", 1.85, 2.6)


def _entre(som: np.ndarray, a: Palavra = CEDO_A, b: Palavra = CEDO_B) -> fronteiras.Pausa:
    achada = fronteiras.entre(fronteiras.atividade(som, TAXA), a, b)
    assert achada is not None
    return achada


class TestAsBordas:
    def test_no_som_e_nao_no_whisper(self):
        achada = _entre(_duas_falas())
        assert achada.fim_da_fala == pytest.approx(1.2, abs=PERTO)
        assert achada.comeco_da_fala == pytest.approx(2.0, abs=PERTO)
        assert achada.duracao == pytest.approx(0.8, abs=2 * PERTO)

    def test_o_s_do_comeco_e_da_palavra(self):
        """O "s" de "síntese" só aparece na faixa de cima: pela energia toda, a palavra
        começaria na vogal, 150 ms depois."""
        som = _fundo()
        _vogal(som, 0.5, 1.2)
        _chiado(som, 2.0, 2.15, amplitude=0.05)
        _vogal(som, 2.15, 2.6)
        assert _entre(som).comeco_da_fala == pytest.approx(2.0, abs=PERTO)

    def test_a_cauda_que_some_devagar_e_da_palavra(self):
        """O "ã" de "manhã" some aos poucos: a borda vem depois da cauda, e não onde ela
        começa a cair."""
        som = _fundo()
        _vogal(som, 0.5, 1.2)
        t = _tempo()
        cauda = (t >= 1.2) & (t < 1.5)
        onda = sum(np.sin(2 * np.pi * 180 * h * t[cauda]) / h for h in range(1, 21))
        som[cauda] += 0.15 * onda * np.exp(-(t[cauda] - 1.2) * 15)
        _vogal(som, 2.0, 2.6)
        assert _entre(som).fim_da_fala >= 1.35


class TestOQueNaoPartaAPausa:
    def test_um_respiro(self):
        """Antes de "Nela", um respiro longe da fala: a pausa continua uma só, e o começo
        fica na palavra, e não no respiro."""
        som = _fundo()
        _vogal(som, 0.5, 1.1)
        _chiado(som, 1.1, 1.2, amplitude=0.05)               # o "s" de "pessoas"
        _chiado(som, 1.5, 1.75, amplitude=0.003, acima_hz=200, semente=3)
        _vogal(som, 2.0, 2.6)
        achada = _entre(som)
        assert achada.fim_da_fala == pytest.approx(1.2, abs=PERTO)
        assert achada.comeco_da_fala == pytest.approx(2.0, abs=PERTO)

    def test_um_estalo_da_boca(self):
        som = _duas_falas()
        t = _tempo()
        som[(t >= 1.6) & (t < 1.601)] += 0.4
        achada = _entre(som)
        assert achada.fim_da_fala == pytest.approx(1.2, abs=PERTO)
        assert achada.comeco_da_fala == pytest.approx(2.0, abs=PERTO)

    def test_o_ronco_grave(self):
        """Abaixo de 150 Hz, o ar e a mesa chegam a passar a fala nas pausas."""
        som = _duas_falas()
        som += 0.05 * np.sin(2 * np.pi * 50 * _tempo())
        achada = _entre(som)
        assert achada.fim_da_fala == pytest.approx(1.2, abs=PERTO)
        assert achada.comeco_da_fala == pytest.approx(2.0, abs=PERTO)

    def test_o_portao_de_ruido(self):
        """Zeros no meio da pausa (o portão fechou) e o ruído da sala perto da fala: o fundo
        não vai aos zeros, e a sala não vira palavra."""
        som = _fundo(-55.0)
        _vogal(som, 0.5, 1.1)
        _chiado(som, 1.1, 1.2, amplitude=0.05)
        _vogal(som, 2.0, 2.6)
        t = _tempo()
        som[(t >= 1.4) & (t < 1.8)] = 0.0
        achada = _entre(som)
        assert achada.fim_da_fala == pytest.approx(1.2, abs=PERTO)
        assert achada.comeco_da_fala == pytest.approx(2.0, abs=PERTO)


class TestQualPausa:
    def test_o_whisper_poe_a_palavra_no_silencio(self):
        """ "Que" no Whisper de 1,4 a 1,7 s; o som, de 2,0 a 2,6 s."""
        b = Palavra("Que", 1.4, 1.7)
        assert _entre(_duas_falas(), b=b).comeco_da_fala == pytest.approx(2.0, abs=PERTO)

    def test_o_fechamento_do_t_nao_e_a_pausa(self):
        """O "t" dentro da palavra seguinte também é silêncio (40 ms), mas a pausa é a que
        cobre o vão do Whisper."""
        som = _fundo()
        _vogal(som, 0.5, 1.2)
        _vogal(som, 2.0, 2.2)
        _vogal(som, 2.24, 2.6)
        achada = _entre(som)
        assert achada.comeco_da_fala == pytest.approx(2.0, abs=PERTO)

    def test_sem_pausa_fica_o_whisper(self):
        som = _fundo()
        _vogal(som, 0.2, 2.8)
        medida = fronteiras.atividade(som, TAXA)
        assert fronteiras.entre(medida, CEDO_A, CEDO_B) is None
        assert fronteiras.comeco(medida, CEDO_B, CEDO_A) == CEDO_B.inicio
        assert fronteiras.fim(medida, CEDO_A, CEDO_B) == CEDO_A.fim

    def test_a_primeira_e_a_ultima_palavra(self):
        medida = fronteiras.atividade(_duas_falas(), TAXA)
        assert fronteiras.comeco(medida, Palavra("antes", 0.3, 1.1)) == pytest.approx(
            0.5, abs=PERTO)
        assert fronteiras.fim(medida, Palavra("depois", 2.0, 2.4), duracao=DURACAO) == \
            pytest.approx(2.6, abs=PERTO)


class TestAMedida:
    def test_nao_depende_do_bloco(self, monkeypatch):
        """O filtro das faixas tem rampas: com o corte seco, a ponta do trecho medido vazava
        para as pausas, e a borda mudava conforme onde o áudio era cortado."""
        som = _duas_falas()
        inteira = fronteiras.atividade(som, TAXA)
        monkeypatch.setattr(fronteiras, "BLOCO_S", 0.7)
        em_blocos = fronteiras.atividade(som, TAXA)
        for a, b in zip(inteira.cruas, em_blocos.cruas, strict=True):
            assert np.max(np.abs(a - b)) < 1.0
        assert fronteiras.entre(em_blocos, CEDO_A, CEDO_B) == fronteiras.entre(
            inteira, CEDO_A, CEDO_B)

    def test_audio_curto_e_vazio(self):
        assert fronteiras.entre(fronteiras.atividade(np.zeros(100), TAXA), CEDO_A, CEDO_B) is None
        assert fronteiras.atividade(np.zeros(0), TAXA).cruas[0].size == 0
