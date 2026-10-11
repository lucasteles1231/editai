"""
Os efeitos na voz: o texto do efeito, o que cada controle promete (medido num sinal de voz
sintético, com a F0 conhecida), os prontos, os seus e onde o efeito entra na edição.

A F0 da saída é medida pelo cepstro, e não pelo YIN que a afinação usa: um juiz que erra
do mesmo jeito que o julgado aprovaria o erro. O medidor é conferido antes contra a F0
verdadeira da entrada.
"""
from __future__ import annotations

import json
import re
import time
import wave

import numpy as np
import pytest

from editor import efeitos_da_voz as ef
from editor import render, voz
from editor.opcoes import OpcoesDeEdicao

T = ef.TAXA


def vogal(f0_ini: float = 150.0, f0_fim: float = 250.0, segundos: float = 3.0,
          silencio_s: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    """Uma voz sintética: pulsos glotais com a F0 deslizando, três formantes (700, 1200 e
    2600 Hz) e sílabas (o volume sobe e desce 2 vezes por segundo). Devolve o áudio e a
    F0 verdadeira de cada amostra."""
    n = int(segundos * T)
    f0 = np.geomspace(f0_ini, f0_fim, n)
    fase = np.cumsum(f0) / T
    pulsos = np.zeros(n, np.float32)
    pulsos[np.flatnonzero(np.diff(np.floor(fase)) > 0)] = 1.0
    x = voz.filtrar(pulsos, "equalizer=f=700:t=q:w=6:g=18,equalizer=f=1200:t=q:w=6:g=15,"
                            "equalizer=f=2600:t=q:w=6:g=12,lowpass=f=5000")
    x = x * (0.5 + 0.5 * np.sin(2 * np.pi * 2 * np.arange(n) / T))
    x = (x / np.abs(x).max() * 0.5).astype(np.float32)
    if silencio_s:
        x = np.concatenate([x, np.zeros(int(silencio_s * T), np.float32)])
        f0 = np.concatenate([f0, np.zeros(int(silencio_s * T))])
    return x, f0


def f0_cepstro(x: np.ndarray, ini: float, dur: float = 0.08) -> float:
    a, m = int(ini * T), int(dur * T)
    espectro = np.log(np.abs(np.fft.rfft(x[a:a + m] * np.hanning(m), 1 << 15)) + 1e-9)
    cep = np.fft.irfft(espectro)
    q = np.arange(len(cep)) / T
    faixa = (q > 1 / 600) & (q < 1 / 70)
    return float(1 / q[faixa][np.argmax(cep[faixa])])


def cents_da_nota(f: np.ndarray) -> np.ndarray:
    m = 69 + 12 * np.log2(np.asarray(f) / 440)
    return np.abs(m - np.round(m)) * 100


#: Fora dos vales do volume (o seno das sílabas zera em 0,75 s, 1,25 s...).
TEMPOS = np.array([t for t in np.arange(0.2, 2.75, 0.05) if abs((t + 0.04) % 0.5 - 0.25) > 0.12])


@pytest.fixture(scope="module")
def entrada():
    return vogal()


class TestOTexto:
    def test_ida_e_volta(self):
        e = ef.ler("coral=20; TOM=+9  agudos=3")
        assert e == {"tom": 9, "coral": 20, "agudos": 3}
        assert ef.escrever(e) == "tom=9,coral=20,agudos=3"      # a ordem dos controles
        assert ef.normalizar(" tom=0, eco=0 ") == ""            # os zeros saem
        assert ef.ler("") == {} and ef.ler(None) == {}

    @pytest.mark.parametrize(("texto", "pedaco"), [
        ("pato=3", "efeito desconhecido: pato"),
        ("tom=13", "Tom vai de −12 a +12 semitons"),
        ("robo=101", "Robô vai de 0 a 100 %"),
        ("graves=-13", "Graves vai de −12 a +12 dB"),
        ("tom=1.5", "número inteiro"),
        ("tom", "número inteiro"),
    ])
    def test_recusa_com_o_motivo(self, texto, pedaco):
        with pytest.raises(ef.EfeitoInvalido, match=re.escape(pedaco)):
            ef.ler(texto)

    def test_nas_opcoes_de_edicao(self):
        assert OpcoesDeEdicao(efeito_da_voz="tom=9").problemas() == []
        erros = OpcoesDeEdicao(efeito_da_voz="tom=40").problemas()
        assert erros and "efeito na voz" in erros[0]

    def test_resolver_pelo_nome_pelo_titulo_e_pelos_ajustes(self):
        assert ef.resolver("esquilo") == ef.PRONTOS["esquilo"].efeito
        assert ef.resolver("Rádio antigo") == ef.PRONTOS["radio-antigo"].efeito
        assert ef.resolver("eco=30, tom=-2") == "tom=-2,eco=30"
        with pytest.raises(ef.EfeitoInvalido, match="efeito desconhecido"):
            ef.resolver("pato")


class TestOMedidor:
    def test_o_cepstro_acerta_a_f0_da_entrada(self, entrada):
        """O juiz primeiro: contra a F0 verdadeira, a menos de 10 cents na mediana."""
        x, f0 = entrada
        verdade = np.array([f0[int((t + 0.04) * T)] for t in TEMPOS])
        medida = np.array([f0_cepstro(x, t) for t in TEMPOS])
        erro = np.abs(1200 * np.log2(medida / verdade))
        assert np.median(erro) < 10
        assert np.mean(erro < 50) > 0.9


class TestCadaControle:
    def test_o_tom_muda_a_f0_e_nao_a_duracao(self, entrada):
        x, f0 = entrada
        for semitons in (12, -7):
            y = ef.aplicar_na_voz(x, {"tom": semitons})
            assert len(y) == len(x)
            for t in (0.5, 1.5, 2.5):
                esperado = f0[int((t + 0.04) * T)] * 2 ** (semitons / 12)
                assert abs(1200 * np.log2(f0_cepstro(y, t) / esperado)) < 30

    def test_o_tom_nao_escorrega_no_tempo(self, entrada):
        """A legenda é a da voz sem efeito: a saída não pode adiantar nem atrasar."""
        x, _ = entrada
        y = ef.aplicar_na_voz(x, {"tom": 9})

        def envelope(z):
            e = np.convolve(np.abs(z), np.ones(480) / 480, mode="same")[::48]   # 1 ms
            return e - e.mean()

        c = np.correlate(envelope(y), envelope(x), mode="full")
        assert abs(int(np.argmax(c)) - (len(envelope(x)) - 1)) <= 20             # ms

    def test_a_afinacao_poe_a_voz_nas_notas(self, entrada):
        x, f0 = entrada
        verdade = np.array([f0[int((t + 0.04) * T)] for t in TEMPOS])
        y = ef.aplicar_na_voz(x, {"afinacao": 100})
        saida = np.array([f0_cepstro(y, t) for t in TEMPOS])
        assert np.mean(cents_da_nota(verdade) < 25) < 0.6          # a entrada desliza
        assert np.mean(cents_da_nota(saida) < 25) >= 0.8           # a saída para nas notas
        # e continua perto de onde estava (a nota mais perto, não outra)
        assert np.median(np.abs(1200 * np.log2(saida / verdade))) < 60

    def test_o_robo_zumbe_no_tom_dele(self, entrada):
        x, _ = entrada
        y = ef.aplicar_na_voz(x, {"robo": 100})
        f = np.array([f0_cepstro(y, t) for t in TEMPOS])
        # a voz ia de 150 a 250 Hz; o robô fica parado no zumbido
        assert np.mean(np.abs(f - ef.ROBO_HZ) < 6) > 0.8

    def test_o_sussurro_tira_a_voz(self, entrada):
        x, _ = entrada

        def harmonia(z):
            notas = []
            for t in TEMPOS:
                s = z[int(t * T): int((t + 0.08) * T)].astype(np.float64)
                s = s - s.mean()
                r = np.correlate(s, s, mode="full")[len(s) - 1:]
                lags = slice(int(T / 400), int(T / 100))
                notas.append(r[lags].max() / (r[0] + 1e-12))
            return float(np.median(notas))

        assert harmonia(x) > 0.6
        assert harmonia(ef.aplicar_na_voz(x, {"sussurro": 100})) < 0.35

    def test_o_radio_estreita_a_faixa(self, entrada):
        x, _ = entrada

        def faixas(z):
            m = np.abs(np.fft.rfft(z)) ** 2
            f = np.fft.rfftfreq(len(z), 1 / T)
            meio = m[(f > 700) & (f < 2000)].mean()
            return (10 * np.log10(m[(f > 60) & (f < 250)].mean() / meio),
                    10 * np.log10(m[(f > 4000) & (f < 6000)].mean() / meio))

        graves_x, agudos_x = faixas(x)
        graves_y, agudos_y = faixas(ef.aplicar_na_voz(x, {"radio": 100}))
        assert graves_y < graves_x - 10 and agudos_y < agudos_x - 10

    @pytest.mark.parametrize("controle", ["eco", "sala"])
    def test_o_eco_e_a_sala_deixam_cauda(self, controle):
        x, _ = vogal(segundos=2.0, silencio_s=1.0)
        y = ef.aplicar_no_ambiente(np.stack([x, x], axis=1), {controle: 80})
        assert y.shape == (len(x), 2)
        cauda = y[int(2.1 * T): int(2.6 * T)]
        assert np.sqrt(np.mean(cauda ** 2)) > 10 ** (-45 / 20)
        assert np.abs(y[-int(0.01 * T):]).max() < 0.05             # o fim some, sem estalo

    def test_o_coral_abre_o_estereo(self, entrada):
        x, _ = entrada
        y = ef.aplicar_no_ambiente(np.stack([x, x], axis=1), {"coral": 60})
        assert np.corrcoef(y[:, 0], y[:, 1])[0, 1] < 0.98

    def test_o_volume_fica_o_mesmo(self, entrada):
        x, _ = entrada
        for efeito in ({"tom": 9}, {"distorcao": 80}, {"radio": 100, "graves": 6}):
            assert abs(voz.lufs(ef.aplicar_na_voz(x, efeito)) - voz.lufs(x)) < 1.0

    def test_sem_efeito_volta_igual(self, entrada):
        x, _ = entrada
        assert ef.aplicar_na_voz(x, {}) is not None
        assert np.array_equal(ef.aplicar_na_voz(x, {"eco": 50}), x)   # o eco é do ambiente
        estereo = np.stack([x, x], axis=1)
        assert np.array_equal(ef.aplicar_no_ambiente(estereo, {"tom": 5}), estereo)


class TestOsProntos:
    @pytest.mark.parametrize("nome", list(ef.PRONTOS))
    def test_cada_pronto(self, entrada, nome):
        x, _ = entrada
        p = ef.PRONTOS[nome]
        assert p.titulo and p.frase and ef.normalizar(p.efeito) == p.efeito
        y = ef.aplicar(x, ef.ler(p.efeito))
        assert y.shape == (len(x), 2)                               # ao pé da amostra
        assert np.isfinite(y).all() and np.abs(y).max() <= 10 ** (voz.PICO_DB / 20) + 1e-4
        assert np.sqrt(np.mean(y ** 2)) > 0.01                       # não ficou mudo
        assert np.abs(y[:, 0] - x).mean() > 0.3 * np.abs(x).mean()   # e mudou

    def test_dois_prontos_nunca_sao_iguais(self):
        efeitos = [p.efeito for p in ef.PRONTOS.values()]
        assert len(set(efeitos)) == len(efeitos)

    def test_a_afinacao_e_rapida(self):
        """Um minuto de voz a 48 kHz: medido em 0,75 s num M5 (10/10)."""
        x, _ = vogal(segundos=60.0)
        t0 = time.perf_counter()
        ef.aplicar_na_voz(x, {"afinacao": 100})
        assert time.perf_counter() - t0 < 15


class TestOsSeus:
    def test_salvar_substituir_e_apagar(self):
        e = ef.salvar({"titulo": "Meu robô", "efeito": "robo=70, eco=20"})
        assert (e.nome, e.efeito, e.meu) == ("meu-robo", "robo=70,eco=20", True)
        assert [x.nome for x in ef.meus()] == ["meu-robo"]
        with pytest.raises(ef.EfeitoJaExiste):
            ef.salvar({"titulo": "Meu Robô!", "efeito": "robo=10"})
        ef.salvar({"titulo": "Meu Robô!", "efeito": "robo=10"}, substituir=True)
        assert [x.efeito for x in ef.meus()] == ["robo=10"]
        assert "meu-robo" in ef.todos() and list(ef.todos())[: len(ef.PRONTOS)] == list(ef.PRONTOS)
        ef.apagar("meu-robo")
        assert ef.meus() == []
        with pytest.raises(ef.EfeitoInvalido):
            ef.apagar("esquilo")                                    # pronto não se apaga

    @pytest.mark.parametrize(("dados", "pedaco"), [
        ({"titulo": "Esquilo", "efeito": "tom=3"}, "efeito pronto"),
        ({"titulo": "radio antigo", "efeito": "tom=3"}, "efeito pronto"),
        ({"titulo": "Nada", "efeito": "tom=0"}, "não muda nada"),
        ({"titulo": "", "efeito": "tom=3"}, "Dê um nome"),
        ({"titulo": "x" * 41, "efeito": "tom=3"}, "passa de 40"),
        ({"titulo": "Torto", "efeito": "tom=99"}, "Tom vai de"),
    ])
    def test_recusados(self, dados, pedaco):
        with pytest.raises(ef.EfeitoInvalido, match=re.escape(pedaco)):
            ef.salvar(dados)

    def test_o_teto(self, monkeypatch):
        monkeypatch.setattr(ef, "TETO", 2)
        ef.salvar({"titulo": "Um", "efeito": "tom=1"})
        ef.salvar({"titulo": "Dois", "efeito": "tom=2"})
        with pytest.raises(ef.EfeitoInvalido, match="Cabem até 2"):
            ef.salvar({"titulo": "Três", "efeito": "tom=3"})

    def test_arquivo_estragado_e_item_torto_ficam_de_lado(self, caplog):
        destino = ef.arquivo_dos_meus()
        destino.write_text("{não é json", encoding="utf-8")
        assert ef.meus() == []
        destino.write_text(json.dumps({"efeitos": [
            {"titulo": "Bom", "efeito": "tom=2"}, {"titulo": "Ruim", "efeito": "tom=50"}]}),
            encoding="utf-8")
        assert [e.titulo for e in ef.meus()] == ["Bom"]
        assert "deixado de lado" in caplog.text

    def test_o_json_da_pagina(self):
        j = ef.para_json()
        assert [c["chave"] for c in j["controles"]] == [c.chave for c in ef.CONTROLES]
        assert {c["grupo"] for c in j["controles"]} == {"tom", "carater", "ambiente",
                                                         "equalizador"}
        assert [e["nome"] for e in j["efeitos"]] == list(ef.PRONTOS)


def _wav(caminho, x):
    with wave.open(str(caminho), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(T)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())
    return caminho


class TestNaEdicao:
    def _preparar(self, arquivo, **opcoes):
        return render._preparar_fala([arquivo], OpcoesDeEdicao(**opcoes),
                                     lambda *_a: None, lambda: False)

    def test_com_efeito_nao_vai_o_original(self, tmp_path, entrada):
        arquivo = _wav(tmp_path / "fala.wav", entrada[0])
        assert self._preparar(arquivo).arquivo == arquivo           # o atalho de sempre
        com = self._preparar(arquivo, efeito_da_voz="tom=9,eco=30")
        assert com.arquivo != arquivo and com.arquivo.is_file()

    def test_mesma_duracao_e_outra_chave(self, tmp_path, entrada):
        arquivo = _wav(tmp_path / "fala.wav", entrada[0])
        sem = self._preparar(arquivo, voz="limpa")
        com = self._preparar(arquivo, voz="limpa", efeito_da_voz="afinacao=100,sala=40")
        assert com.arquivo != sem.arquivo
        assert com.duracao == sem.duracao
        with wave.open(str(com.arquivo)) as w:
            assert w.getnframes() == round(sem.duracao * T) and w.getnchannels() == 2
        assert [w.texto for w in com.palavras] == [w.texto for w in sem.palavras]

    def test_o_bipe_continua_no_lugar(self, tmp_path, entrada):
        arquivo = _wav(tmp_path / "fala.wav", entrada[0])
        sem = self._preparar(arquivo, voz="limpa", bipe="olá")
        com = self._preparar(arquivo, voz="limpa", bipe="olá", efeito_da_voz="eco=60")
        assert com.bipes == sem.bipes
