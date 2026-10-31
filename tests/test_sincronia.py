"""
O áudio gravado à parte (editor/sincronia.py), com uma fala sintética em que o atraso e a
deriva são conhecidos: a câmera ouve a mesma fala, mais longe, com outra cor e com chiado.
"""
from __future__ import annotations

import numpy as np
import pytest

from editor import sincronia

TAXA = sincronia.TAXA


def fala(segundos: float, semente: int = 1) -> np.ndarray:
    """Sílabas de 80 a 300 ms (um tom com harmônicos e um pouco de sopro), com pausas de 50
    a 400 ms entre elas, como uma fala."""
    rng = np.random.default_rng(semente)
    x = np.zeros(int(segundos * TAXA), dtype=np.float64)
    t = 0.2
    while t < segundos - 0.5:
        dur = rng.uniform(0.08, 0.3)
        n = int(dur * TAXA)
        i = int(t * TAXA)
        tempo = np.arange(n) / TAXA
        f0 = rng.uniform(100, 220)
        som = sum(np.sin(2 * np.pi * f0 * h * tempo + rng.uniform(0, 6)) / h for h in range(1, 6))
        som = som + 0.3 * rng.standard_normal(n)
        envelope = np.sin(np.pi * np.arange(n) / n) ** 2
        x[i:i + n] += som * envelope * rng.uniform(0.3, 1.0)
        t += dur + rng.uniform(0.05, 0.4)
    return (x / np.abs(x).max() * 0.8).astype(np.float32)


def na_camera(x: np.ndarray, atraso_s: float, deriva: float = 0.0, segundos: float | None = None,
              semente: int = 9) -> np.ndarray:
    """O que a câmera ouviu: ``x`` no tempo dela (``atraso_s + t * (1 + deriva)``), abafado,
    mais baixo e com chiado a uns 10 dB."""
    rng = np.random.default_rng(semente)
    segundos = segundos if segundos is not None else len(x) / TAXA + atraso_s
    tau = np.arange(int(segundos * TAXA)) / TAXA
    origem = (tau - atraso_s) / (1 + deriva) * TAXA
    dentro = (origem >= 0) & (origem < len(x) - 1)
    y = np.zeros_like(tau)
    y[dentro] = np.interp(origem[dentro], np.arange(len(x)), x)
    y = np.convolve(y, [0.25, 0.5, 0.25], mode="same") * 0.3        # outro microfone
    chiado = rng.standard_normal(len(y)) * np.sqrt(np.mean(y ** 2)) / 3
    return (y + chiado).astype(np.float32)


@pytest.mark.parametrize("atraso_s", [2.3456, -3.2104, 0.0])
def test_o_atraso_na_amostra(atraso_s):
    x = fala(40.0)
    a = sincronia.medir(na_camera(x, atraso_s), x)
    assert a.ok and a.confianca >= sincronia.CONFIANCA_MINIMA
    assert a.atraso_s == pytest.approx(atraso_s, abs=0.001)
    assert a.deriva == 0.0 and len(a.medidas) == 3


def test_um_clipe_curto_acha_o_lugar_num_audio_longo():
    x = fala(90.0, semente=4)
    clipe = na_camera(x, -51.37, segundos=12.0)       # a câmera ligou 51,37 s depois
    a = sincronia.medir(clipe, x)
    assert a.ok and a.atraso_s == pytest.approx(-51.37, abs=0.001)
    assert a.no_video(51.37 + 3.0) == pytest.approx(3.0, abs=0.001)


def test_a_deriva_dos_relogios():
    """150 ppm em 5 min separam 45 ms (mais que um quadro): a reta das três medidas pega."""
    x = fala(300.0, semente=7)
    a = sincronia.medir(na_camera(x, 1.5, deriva=150e-6), x)
    assert a.ok and a.deriva_ppm == pytest.approx(150, abs=10)
    for t in (10.0, 150.0, 290.0):
        assert a.no_video(t) == pytest.approx(1.5 + t * (1 + 150e-6), abs=0.5 / 30)


def test_a_deriva_pequena_nao_entra():
    x = fala(60.0, semente=3)
    a = sincronia.medir(na_camera(x, 0.8, deriva=20e-6), x)      # 1,2 ms no arquivo inteiro
    assert a.deriva == 0.0 and a.atraso_s == pytest.approx(0.8, abs=0.002)


def test_sons_de_gravacoes_diferentes_nao_confiam():
    a = sincronia.medir(na_camera(fala(30.0, semente=11), 0.0), fala(30.0, semente=12))
    assert not a.ok and a.confianca < sincronia.CONFIANCA_MINIMA


def test_curto_demais():
    with pytest.raises(sincronia.SemSincronia):
        sincronia.medir(np.zeros(100, np.float32), np.zeros(100, np.float32))


def test_o_dicionario():
    x = fala(20.0)
    d = sincronia.medir(na_camera(x, 1.0), x).para_dict()
    assert set(d) == {"atraso_s", "deriva_ppm", "confianca", "ok", "medidas"} and d["ok"]


def _para_48k(y: np.ndarray) -> np.ndarray:
    return np.interp(np.arange(len(y) * 3) / 3, np.arange(len(y)), y).astype(np.float32)


def _wav(caminho, y: np.ndarray) -> None:
    import wave

    with wave.open(str(caminho), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(48_000)
        w.writeframes((np.clip(y, -1, 1) * 32767).astype("<i2").tobytes())


def test_a_montagem_le_o_video_no_tempo_do_som(tmp_path):
    """O vídeo da câmera (com o som ruim dela) e o microfone à parte: a edição acha o atraso,
    lê o vídeo no tempo do som, e o resultado diz o atraso achado."""
    from editor import render
    from editor import saida as saida_mod
    from editor.montagem import Montagem
    from editor.opcoes import OpcoesDeEdicao
    from tests.conftest import fazer_video

    x = fala(12.0, semente=5)
    camera_16k = na_camera(x, 1.25, segundos=14.0)
    som = _para_48k(camera_16k)
    camera = fazer_video(tmp_path / "camera.mp4", segundos=14.0, audio=np.stack([som, som], 1))
    microfone = tmp_path / "microfone.wav"
    _wav(microfone, _para_48k(x))
    m = Montagem(camera, audios=(microfone,), fala="audio", sincronizar=True)
    assert m.problemas() == [] and m.video_da_camera() == camera
    avisos = []
    r = render.editar(None, tmp_path / "saida.mp4", OpcoesDeEdicao(), saida_mod.OpcoesDeSaida(),
                      montagem=m, progresso=lambda e, f, d: avisos.append((e, d)))
    assert r.sincronia["ok"] and r.sincronia["atraso_s"] == pytest.approx(1.25, abs=0.03)
    assert any(e == "sincronizando" and "+1.2" in d for e, d in avisos)
    assert (tmp_path / "saida.mp4").stat().st_size > 1000


def test_o_ajuste_a_mao(tmp_path):
    from editor import render
    from editor import saida as saida_mod
    from editor.montagem import Montagem
    from editor.opcoes import OpcoesDeEdicao
    from tests.conftest import fazer_video

    camera = fazer_video(tmp_path / "camera.mp4", segundos=3.0)
    microfone = tmp_path / "microfone.wav"
    _wav(microfone, fala(3.0))
    m = Montagem(camera, audios=(microfone,), fala="audio", atraso_s=-0.4)
    r = render.editar(None, tmp_path / "saida.mp4", OpcoesDeEdicao(), saida_mod.OpcoesDeSaida(),
                      montagem=m)
    assert r.sincronia == {"atraso_s": -0.4, "deriva_ppm": 0.0, "confianca": None, "ok": True,
                           "medidas": []}


def test_o_que_a_montagem_pede():
    from pathlib import Path

    from editor.montagem import Montagem

    dois = Montagem(Path("v.mp4"), audios=(Path("a.wav"), Path("b.wav")), sincronizar=True)
    assert any("um arquivo só" in e for e in dois.problemas())
    sem_audio = Montagem(Path("v.mp4"), fala="fundo", sincronizar=True)
    assert any("gravado à parte" in e for e in sem_audio.problemas())
    com_pessoa = Montagem(Path("tela.mp4"), pessoa=Path("eu.mp4"), audios=(Path("a.wav"),))
    assert com_pessoa.video_da_camera() == Path("eu.mp4")


def test_o_cursor_no_outro_tempo():
    from editor import video as video_mod

    class Falso:
        duracao = 10.0

        def em(self, t):
            return t

    falso = Falso()
    c = video_mod.NoTempo(falso, lambda t: t + 2.0)
    assert c.em(3.0) == 5.0
    assert c.em(-5.0) == 0.0                     # antes de a câmera ligar: o primeiro quadro
    assert c.em(30.0) == pytest.approx(9.999)    # depois de ela desligar: o último, sem loop
