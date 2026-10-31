"""
O ruído da fala (editor/ruido.py): a régua do Auto, a limpeza no tempo certo (com um modelo de
mentira que atrasa a saída como o de verdade), o download conferido pelo SHA-256, a edição
com e sem o modelo e o pedido do ok.
"""
from __future__ import annotations

import hashlib
import wave

import httpx
import numpy as np
import pytest

from editor import componentes, render, ruido, voz
from tests.test_sincronia import fala

TAXA = ruido.TAXA


def _para_48k(y: np.ndarray) -> np.ndarray:
    return np.interp(np.arange(len(y) * 3) / 3, np.arange(len(y)), y).astype(np.float32)


def _com_ruido(segundos: float = 6.0, snr_db: float = 8.0) -> np.ndarray:
    x = _para_48k(fala(segundos, semente=2))
    rng = np.random.default_rng(5)
    chiado = rng.standard_normal(len(x)).astype(np.float32)
    chiado *= float(np.sqrt(np.mean(x ** 2))) / float(np.sqrt(np.mean(chiado ** 2)))
    return (x + chiado * 10 ** (-snr_db / 20)).astype(np.float32)


def _wav(caminho, y: np.ndarray) -> None:
    with wave.open(str(caminho), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(TAXA)
        w.writeframes((np.clip(y, -1, 1) * 32767).astype("<i2").tobytes())


class TestARegua:
    def test_o_silencio_digital_conta_como_limpa(self):
        x = _para_48k(fala(8.0))                # sílabas e zeros entre elas
        assert ruido.medir(x) == ruido.FOLGA_DA_LIMPA
        assert ruido.forca("auto", ruido.medir(x)) == "nada"

    def test_com_chiado_o_auto_limpa(self):
        folga = ruido.medir(_com_ruido(snr_db=8.0))
        assert folga < ruido.FORTE_ABAIXO_DE_DB
        assert ruido.forca("auto", folga) == "forte"
        assert ruido.forca("auto", 22.0) == "leve" and ruido.forca("auto", 31.0) == "nada"

    def test_quem_escolhe_manda(self):
        assert ruido.forca("leve", 99.0) == "leve" and ruido.forca("forte", 99.0) == "forte"
        assert ruido.forca("nao", 3.0) == "nada"

    def test_o_fundo_que_varia_fica_no_auto(self):
        """A música e o som do jogo variam: o Auto não mexe (o modelo os tiraria junto)."""
        rng = np.random.default_rng(8)
        x = _para_48k(fala(8.0, semente=3))
        t = np.arange(len(x)) / TAXA
        # um fundo que sobe e desce como música, a cada meio segundo
        musica = rng.standard_normal(len(x)).astype(np.float32)
        musica *= 0.05 + 0.04 * np.sin(2 * np.pi * t)
        com_musica = (x + musica).astype(np.float32)
        variacao = ruido.variacao_do_fundo(com_musica)
        assert variacao > ruido.FUNDO_CONSTANTE_DB
        assert ruido.forca("auto", ruido.medir(com_musica), variacao) == "nada"
        assert ruido.forca("leve", ruido.medir(com_musica), variacao) == "leve"
        assert ruido.variacao_do_fundo(_com_ruido(snr_db=8.0)) < ruido.FUNDO_CONSTANTE_DB

    def test_varios_arquivos_vale_o_mais_ruidoso(self, monkeypatch, tmp_path):
        folgas = {"a.wav": (40.0, 0.5), "b.wav": (12.0, 0.5)}
        monkeypatch.setattr(ruido, "medidas_do_arquivo", lambda c: folgas[c.name])
        assert ruido.forca_dos_arquivos("auto", [tmp_path / "a.wav", tmp_path / "b.wav"]) == (
            "forte", 12.0)
        assert ruido.forca_dos_arquivos("nao", [tmp_path / "b.wav"])[0] == "nada"

    def test_o_arquivo_sem_som(self, tmp_path):
        mudo = tmp_path / "mudo.txt"
        mudo.write_text("não é áudio")
        assert ruido.folga_do_arquivo(mudo) == ruido.FOLGA_DA_LIMPA


class _ModeloQueAtrasa:
    """Um modelo de mentira que devolve a entrada 1.536 amostras atrás, como o de verdade,
    e passa um estado de um quadro para o outro."""

    class _Nome:
        def __init__(self, nome):
            self.name = nome

    def __init__(self):
        self.fila = np.zeros(ruido.ATRASO, np.float32)
        self.rodadas = 0

    def get_inputs(self):
        return [self._Nome("input_frame"), self._Nome("estado")]

    def get_outputs(self):
        return [self._Nome("enhanced_audio_frame"), self._Nome("new_estado")]

    def run(self, saidas, feeds):
        assert feeds["estado"].shape == (1,) and feeds["estado"][0] == self.rodadas
        self.rodadas += 1
        quadro = feeds["input_frame"]
        self.fila = np.concatenate([self.fila, quadro])
        saida, self.fila = self.fila[:ruido.QUADRO], self.fila[ruido.QUADRO:]
        return [saida * 0.5, np.array([self.rodadas], np.float32)]


@pytest.fixture
def com_modelo(monkeypatch):
    monkeypatch.delenv(ruido.VARIAVEL_FALSA, raising=False)
    modelo = _ModeloQueAtrasa()
    monkeypatch.setattr(ruido, "instalado", lambda: True)
    monkeypatch.setattr(ruido, "_carregar", lambda: modelo)
    monkeypatch.setattr(ruido, "_estados", {"estado": np.array([0], np.float32)})
    return modelo


class TestALimpeza:
    def test_no_mesmo_tempo_e_comprimento(self, com_modelo):
        x = _com_ruido(3.0)
        andou: list[float] = []
        y = ruido.limpar(x, "forte", andamento=andou.append)
        assert len(y) == len(x) and np.allclose(y, x * 0.5, atol=1e-6)    # o atraso saiu
        assert andou[0] == 0.0 and andou[-1] == 1.0

    def test_o_leve_mistura_a_original_no_mesmo_tempo(self, com_modelo):
        x = _com_ruido(2.0)
        y = ruido.limpar(x, "leve")
        resto = 10 ** (-ruido.LEVE_DB / 20)
        assert np.allclose(y, resto * x + (1 - resto) * x * 0.5, atol=1e-6)

    def test_nada_e_cancelar(self, com_modelo):
        x = _com_ruido(2.0)
        assert ruido.limpar(x, "nada") is not None and com_modelo.rodadas == 0
        with pytest.raises(InterruptedError):
            ruido.limpar(x, "forte", parar=lambda: True)

    def test_sem_o_modelo(self, monkeypatch):
        monkeypatch.delenv(ruido.VARIAVEL_FALSA, raising=False)
        monkeypatch.setattr(ruido, "instalado", lambda: False)
        with pytest.raises(ruido.ErroDoRuido):
            ruido.limpar(_com_ruido(1.0), "forte")


class TestOBaixar:
    @pytest.fixture
    def release(self, monkeypatch, tmp_path):
        conteudos = {ruido.MODELO: b"o modelo" * 1000, ruido.ESTADOS: b"os estados" * 50}
        monkeypatch.setattr(ruido, "ARQUIVOS", {n: (hashlib.sha256(c).hexdigest(), len(c))
                                                for n, c in conteudos.items()})
        monkeypatch.setattr(ruido, "BYTES", sum(len(c) for c in conteudos.values()))
        monkeypatch.setattr(ruido, "pasta", lambda: tmp_path / "ruido")
        monkeypatch.delenv(ruido.VARIAVEL_FALSA, raising=False)
        pedidos: list[str] = []

        def servir(pedido: httpx.Request) -> httpx.Response:
            pedidos.append(str(pedido.url))
            return httpx.Response(200, content=conteudos[pedido.url.path.rsplit("/", 1)[-1]])

        monkeypatch.setattr(ruido, "_transporte", httpx.MockTransport(servir))
        return conteudos, pedidos

    def test_baixa_confere_e_instala(self, release):
        _conteudos, pedidos = release
        assert not ruido.instalado()
        andou: list[float] = []
        ruido.baixar(lambda f, texto: andou.append(f))
        assert ruido.instalado() and andou[-1] == 1.0 and andou == sorted(andou)
        assert [p.rsplit("/", 1)[-1] for p in pedidos] == [ruido.MODELO, ruido.ESTADOS]
        assert all(p.startswith(ruido.RELEASE) for p in pedidos)
        ruido.baixar()                           # já está: não baixa de novo
        assert len(pedidos) == 2
        assert ruido.desinstalar() > 0 and not ruido.instalado()

    def test_o_trocado_nao_entra(self, release, monkeypatch):
        tamanho = ruido.ARQUIVOS[ruido.MODELO][1]
        monkeypatch.setitem(ruido.ARQUIVOS, ruido.MODELO, ("0" * 64, tamanho))
        with pytest.raises(ruido.ErroDoRuido, match="não confere"):
            ruido.baixar()
        assert not (ruido.pasta() / ruido.MODELO).exists()

    def test_pelo_catalogo_so_com_o_ok(self, release):
        with pytest.raises(componentes.PrecisaDeOk):
            componentes.baixar("ruido")
        componentes.aprovar(["ruido"])
        componentes.baixar("ruido")
        assert componentes.instalado("ruido")
        assert componentes.desinstalar("ruido") > 0 and not componentes.aprovado("ruido")


class TestNaEdicao:
    def _fala(self, tmp_path, x):
        caminho = tmp_path / "fala.wav"
        _wav(caminho, x)
        return caminho

    def test_limpa_antes_de_tratar_e_sem_o_portao(self, tmp_path, monkeypatch):
        from editor.opcoes import OpcoesDeEdicao

        portao: list[int] = []
        monkeypatch.setattr(voz, "tirar_ruido", lambda x, *a, **k: portao.append(1) or x)
        avisos = []
        # a 4 dB, longe da divisa do forte (lido a 16 kHz, o chiado agudo some, e a folga sobe)
        prep = render._preparar_fala([self._fala(tmp_path, _com_ruido(snr_db=4.0))],
                                     OpcoesDeEdicao(voz="estudio"),
                                     lambda e, f, d: avisos.append((e, d)), lambda: False)
        assert prep.ruido["forca"] == "forte" and prep.ruido["por"] == "auto"
        assert prep.ruido["folga_db"] < ruido.FORTE_ABAIXO_DE_DB and "aviso" not in prep.ruido
        assert any(e == "limpando" and "dB abaixo da voz" in d for e, d in avisos)
        assert portao == []                      # o portão de antes não limpa de novo

    def test_sem_o_modelo_segue_como_veio_e_avisa(self, tmp_path, monkeypatch):
        from editor.opcoes import OpcoesDeEdicao

        monkeypatch.setattr(ruido, "instalado", lambda: False)
        arquivo = self._fala(tmp_path, _com_ruido())
        prep = render._preparar_fala([arquivo], OpcoesDeEdicao(), lambda *a: None, lambda: False)
        assert prep.arquivo == arquivo                     # a voz como veio
        assert prep.ruido["aviso"] == "o redutor de ruído não foi baixado"

    def test_a_fala_limpa_nao_passa_pelo_redutor(self, tmp_path):
        from editor.opcoes import OpcoesDeEdicao

        arquivo = self._fala(tmp_path, _para_48k(fala(4.0)))
        prep = render._preparar_fala([arquivo], OpcoesDeEdicao(), lambda *a: None, lambda: False)
        assert prep.arquivo == arquivo and prep.ruido == {}

    def test_o_catalogo_pede_o_redutor_so_com_ruido(self, tmp_path, monkeypatch):
        from editor.opcoes import OpcoesDeEdicao

        monkeypatch.setattr(ruido, "instalado", lambda: False)
        com, sem = self._fala(tmp_path, _com_ruido()), tmp_path / "limpa.wav"
        _wav(sem, _para_48k(fala(4.0)))
        assert "ruido" in componentes.da_edicao(OpcoesDeEdicao(), None, [com])
        assert "ruido" not in componentes.da_edicao(OpcoesDeEdicao(), None, [sem])
        assert "ruido" not in componentes.da_edicao(OpcoesDeEdicao(ruido="nao"), None, [com])
        assert not componentes.pegar("ruido").essencial
