"""
O vídeo longo vira a biblioteca de cenas (editor/separar.py): os cortes achados num vídeo de
planos conhecidos, o preto e o clarão de fora, a tomada longa em pedaços, os clipes no quadro
certo e com o som, e a matriz com uma descrição por tomada.
"""
from __future__ import annotations

import json
from pathlib import Path

import av
import numpy as np
import pytest

from editor import catalogo, separar, video

FPS = 30
LARGURA, ALTURA = 320, 180


def _plano_movendo(cor: tuple[int, int, int]):
    """Faixas de cor andando 3 px por quadro: a câmera correndo, que não é corte."""
    x = np.arange(LARGURA)[None, :]

    def quadro(i: int) -> np.ndarray:
        onda = (np.sin((x + 3 * i) / 18.0) * 0.5 + 0.5)[..., None]
        base = np.array(cor, dtype=np.float32)[None, None, :]
        return np.broadcast_to(base * (0.45 + 0.55 * onda), (ALTURA, LARGURA, 3)).astype(np.uint8)
    return quadro


def _parado(cor: tuple[int, int, int]):
    return lambda i: np.full((ALTURA, LARGURA, 3), cor, dtype=np.uint8)


def _xadrez(i: int) -> np.ndarray:
    y, x = np.mgrid[0:ALTURA, 0:LARGURA]
    casa = ((x // 20 + y // 20) % 2).astype(np.uint8)
    m = np.zeros((ALTURA, LARGURA, 3), np.uint8)
    m[..., 1] = 60 + casa * 160
    return m


#: (segundos, quadro): A com movimento, um clarão, B longa com a câmera andando, o preto, C.
PLANOS = [(2.0, _plano_movendo((230, 60, 40))), (0.3, _parado((255, 255, 255))),
          (6.6, _plano_movendo((40, 90, 230))), (0.5, _parado((0, 0, 0))), (1.5, _xadrez)]


def fazer_video_de_planos(caminho: Path, planos=PLANOS, com_audio: bool = True) -> Path:
    with av.open(str(caminho), "w") as c:
        v = c.add_stream("libx264", rate=FPS, options={"crf": "18", "preset": "ultrafast"})
        v.width, v.height, v.pix_fmt = LARGURA, ALTURA, "yuv420p"
        a = None
        if com_audio:
            a = c.add_stream("aac", rate=48_000)
            a.layout = "stereo"
        n = 0
        for segundos, gerar in planos:
            for i in range(round(segundos * FPS)):
                f = av.VideoFrame.from_ndarray(gerar(i), format="rgb24")
                f.pts = n
                n += 1
                for p in v.encode(f):
                    c.mux(p)
        for p in v.encode():
            c.mux(p)
        if a is not None:
            t = np.arange(round(n / FPS * 48_000)) / 48_000
            som = (0.2 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
            dados = np.ascontiguousarray(np.stack([som, som]))
            for k in range(0, dados.shape[1], 1024):
                af = av.AudioFrame.from_ndarray(np.ascontiguousarray(dados[:, k:k + 1024]),
                                                format="fltp", layout="stereo")
                af.sample_rate = 48_000
                af.pts = k
                for p in a.encode(af):
                    c.mux(p)
            for p in a.encode():
                c.mux(p)
    return caminho


@pytest.fixture(scope="module")
def longo(tmp_path_factory) -> Path:
    return fazer_video_de_planos(tmp_path_factory.mktemp("longo") / "Trailer Ação 2026.mp4")


def test_os_cortes_e_os_trechos(longo):
    a = separar.analisar(longo)
    indices = separar.cortes(a)
    instantes = [round(float(a.tempos[i]), 2) for i in indices]
    # as trocas de plano (A→clarão, clarão→B, preto→C); a câmera andando não corta
    for esperado in (2.0, 2.3, 9.4):
        assert any(abs(t - esperado) < 0.05 for t in instantes), instantes
    assert not any(2.4 < t < 8.85 for t in instantes), "o movimento da câmera virou corte"

    trechos = separar.planejar(a, indices)
    # A inteira; o clarão (0,3 s) e o preto de fora; B (6,6 s) em 3 pedaços; C inteira
    assert [(t.tomada, t.parte, t.partes) for t in trechos] == [
        (0, 1, 1), (1, 1, 3), (1, 2, 3), (1, 3, 3), (2, 1, 1)]
    assert trechos[0].inicio == pytest.approx(0.0, abs=0.04)
    assert trechos[0].fim == pytest.approx(2.0, abs=0.04)
    assert trechos[1].inicio == pytest.approx(2.3, abs=0.04)
    assert trechos[3].fim == pytest.approx(8.9, abs=0.04)
    assert trechos[4].inicio == pytest.approx(9.4, abs=0.04)
    for t in trechos[1:4]:
        assert t.duracao == pytest.approx(2.2, abs=0.05)


def test_os_clipes_no_quadro_certo_e_com_som(longo, tmp_path):
    sep = separar.separar(longo, tmp_path / "cenas")
    nomes = [p.name for _t, p in sep.clipes]
    assert nomes == [f"trailer-acao-2026-00{k}.mp4" for k in range(1, 6)]
    assert sep.tomadas == 3
    for trecho, caminho in sep.clipes:
        info = video.sondar(caminho)
        assert info.tem_audio
        assert info.duracao == pytest.approx(trecho.duracao, abs=0.1)
    # o primeiro quadro de cada clipe é do plano dele: A vermelho, B azul, C verde
    cores = []
    for _t, caminho in sep.clipes:
        m = video.quadro_em(caminho, 0.0).reshape(-1, 3).mean(axis=0)
        cores.append(int(np.argmax(m)))
    assert cores == [0, 2, 2, 2, 1]
    # o som de um pedaço do meio é o tom (não silêncio)
    audio = video.ler_audio(sep.clipes[2][1])
    assert np.abs(audio).max() > 0.1


def test_um_video_sem_som(tmp_path):
    mudo = fazer_video_de_planos(tmp_path / "mudo.mp4", PLANOS[:2] + PLANOS[4:], com_audio=False)
    sep = separar.separar(mudo, tmp_path / "cenas")
    assert sep.clipes and not video.sondar(sep.clipes[0][1]).tem_audio


def test_tudo_preto_nao_tem_cena(tmp_path):
    preto = fazer_video_de_planos(tmp_path / "preto.mp4", [(2.0, _parado((0, 0, 0)))])
    with pytest.raises(ValueError, match="nenhuma cena"):
        separar.separar(preto, tmp_path / "cenas")


def test_uma_descricao_por_tomada(longo, tmp_path, monkeypatch):
    """Só o pedaço do meio de cada tomada vai ao Gemini; os irmãos herdam a descrição."""
    sep = separar.separar(longo, tmp_path / "cenas")
    pedidos: list[list[str]] = []

    def gerar(clipes, **_k):
        pedidos.append([arquivo for _c, arquivo in clipes])
        cenas = [{"id": Path(a).stem, "arquivo": a, "descricao": f"descrita: {a}",
                  "categorias": ["teste"], "personagens": [], "periodo": "dia", "energia": "alta",
                  "monetizacao": "ok", "obs": "", "duracao": 1.0} for _c, a in clipes]
        return catalogo.Geracao(cenas, "gemini", "", 1)

    monkeypatch.setattr(catalogo, "gerar", gerar)
    g = separar.descrever(sep)
    assert pedidos == [["trailer-acao-2026-001.mp4", "trailer-acao-2026-003.mp4",
                        "trailer-acao-2026-005.mp4"]]
    assert [c["arquivo"] for c in g.cenas] == [p.name for _t, p in sep.clipes]
    assert {c["descricao"] for c in g.cenas[1:4]} == {"descrita: trailer-acao-2026-003.mp4"}
    assert g.cenas[2]["duracao"] == pytest.approx(sep.clipes[2][0].duracao, abs=0.01)
    # a matriz é lida pelo editor como a de uma pasta montada à mão
    from editor import cenas
    b = cenas.ler_matriz(json.dumps(g.cenas), [p for _t, p in sep.clipes])
    assert len(b.cenas) == 5


def test_sem_o_gemini_a_descricao_diz_de_onde_veio(longo, tmp_path, monkeypatch):
    from editor import ia

    monkeypatch.delenv(ia.VARIAVEL_FALSA, raising=False)
    monkeypatch.setattr(ia, "ligada", lambda: False)
    sep = separar.separar(longo, tmp_path / "cenas")
    g = separar.descrever(sep)
    assert g.por == "rascunho"
    assert g.cenas[0]["descricao"] == "Trecho de 0:00 a 0:02 do vídeo"
    assert g.cenas[-1]["descricao"] == "Trecho de 0:09 a 0:10 do vídeo"
    assert "descreva" in g.aviso


def test_a_pasta_nova_nao_sobrescreve(tmp_path):
    (tmp_path / "meu-video").mkdir()
    assert separar.pasta_nova(tmp_path, "Meu Vídeo!") == tmp_path / "meu-video-2"
    assert separar.nome_curto("  ") == "cenas"
    assert separar.tamanho_dos_clipes(3840, 2160) == (1920, 1080)
    assert separar.tamanho_dos_clipes(1080, 1920) == (1080, 1920)


def test_no_terminal(longo, tmp_path, monkeypatch, capsys):
    """``editai --separar-cenas VIDEO``: a pasta nova nos vídeos, com os clipes e o cenas.json,
    e o comando para usar."""
    from editor import cli, servidor

    monkeypatch.setattr(servidor, "pasta_de_saida_padrao", lambda: tmp_path / "videos")
    assert cli.main(["--separar-cenas", str(longo), "--assunto", "um trailer"]) == 0
    pasta = tmp_path / "videos" / "cenas" / "trailer-acao-2026"
    matriz = json.loads((pasta / "cenas.json").read_text(encoding="utf-8"))
    assert [c["arquivo"] for c in matriz] == [f"trailer-acao-2026-00{k}.mp4" for k in range(1, 6)]
    saida = capsys.readouterr().out
    assert "5 cenas de 3 tomadas" in saida and "--cenas" in saida
    assert cli.main(["--separar-cenas", str(tmp_path / "nao-existe.mp4")]) == 2
