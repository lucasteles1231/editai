"""
As vozes prontas (editor/voz_pronta.py e editor/voz_local.py): o pedido ao TTS do Gemini (um só
por roteiro, com a direção de locução), o PCM que vira o WAV da narração, o cache que poupa a
cota de 10 por dia, o aviso de cota acabada, e a voz local (o Piper, falso nos testes) com a
leitura do dinheiro e da porcentagem.
"""
from __future__ import annotations

import base64
import json

import httpx
import numpy as np
import pytest

from editor import ia, video, voz_clonada, voz_local, voz_pronta

ROTEIRO = ("Por que o céu é azul?\n\nA luz do Sol tem todas as cores, e o ar espalha mais o "
           "azul.\n\nE você, já tinha reparado?")


def _pcm(segundos: float = 2.0) -> bytes:
    t = np.arange(round(segundos * voz_pronta.TAXA_DO_GEMINI)) / voz_pronta.TAXA_DO_GEMINI
    return (0.4 * np.sin(2 * np.pi * 180 * t) * 32767).astype("<i2").tobytes()


class _Tts:
    def __init__(self, *respostas: httpx.Response):
        self.fila = list(respostas)
        self.pedidos: list[dict] = []
        self.urls: list[str] = []

    def __call__(self, pedido: httpx.Request) -> httpx.Response:
        self.pedidos.append(json.loads(pedido.content))
        self.urls.append(str(pedido.url))
        return self.fila.pop(0)

    @property
    def transporte(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)


def _audio(segundos: float = 2.0) -> httpx.Response:
    dados = base64.b64encode(_pcm(segundos)).decode()
    return httpx.Response(200, json={"candidates": [{"content": {"parts": [
        {"inlineData": {"mimeType": "audio/L16;codec=pcm;rate=24000", "data": dados}}]}}]})


@pytest.fixture
def de_verdade(monkeypatch):
    monkeypatch.delenv(ia.VARIAVEL_FALSA, raising=False)
    monkeypatch.setenv(ia.VARIAVEL_DA_CHAVE, "AIzaSyTESTE-chave-de-mentira-123456")


def test_o_catalogo():
    ids = [v.id for v in voz_pronta.vozes()]
    assert "gemini:Orus" in ids and ids[-1] == "local:faber"
    with pytest.raises(voz_pronta.SemVoz):
        voz_pronta.achar("gemini:Inventada")


def test_narra_num_pedido_so_e_guarda(de_verdade, tmp_path):
    tts = _Tts(_audio(3.0))
    n = voz_pronta.narrar("gemini:Orus", ROTEIRO, tmp_path / "n.wav", transporte=tts.transporte)
    assert len(tts.pedidos) == 1
    assert tts.urls[0].endswith(f"{voz_pronta.MODELO_TTS}:generateContent")
    corpo = tts.pedidos[0]
    texto = corpo["contents"][0]["parts"][0]["text"]
    assert texto.startswith(voz_pronta.DIRECAO) and "Por que o céu é azul?" in texto
    voz_cfg = corpo["generationConfig"]["speechConfig"]["voiceConfig"]
    assert voz_cfg["prebuiltVoiceConfig"]["voiceName"] == "Orus"
    assert corpo["generationConfig"]["responseModalities"] == ["AUDIO"]
    assert 2.5 < n.segundos < 3.5
    assert video.duracao_do_audio(n.caminho) == pytest.approx(n.segundos, abs=0.1)
    assert (tmp_path / "n.roteiro.txt").read_text(encoding="utf-8") == ROTEIRO
    assert voz_pronta.usadas_hoje() == 1 and voz_pronta.restantes_hoje() == voz_pronta.POR_DIA - 1
    # o mesmo roteiro de novo sai do cache, sem pedido
    n2 = voz_pronta.narrar("gemini:Orus", ROTEIRO, tmp_path / "n2.wav",
                           transporte=_Tts().transporte)
    assert n2.reaproveitados == 1 and voz_pronta.usadas_hoje() == 1


def test_roteiro_longo_vai_em_partes(monkeypatch):
    monkeypatch.setattr(voz_pronta, "LETRAS_POR_PEDIDO", 60)
    partes = voz_pronta.partes_do_gemini(ROTEIRO)
    assert len(partes) == 3 and partes[0] == "Por que o céu é azul?"
    assert len(voz_pronta.partes_do_gemini("Curto.\n\nTambém curto.")) == 1


def test_a_cota_acabada_vira_aviso(de_verdade, tmp_path):
    erro = {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "details": [
        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "7200s"}]}}
    tts = _Tts(httpx.Response(429, json=erro))
    with pytest.raises(voz_pronta.SemVoz, match=r"cota de voz do Gemini acabou.*2 h"):
        voz_pronta.narrar("gemini:Kore", ROTEIRO, tmp_path / "n.wav", transporte=tts.transporte)
    assert voz_pronta.usadas_hoje() == 0


def test_sem_chave_diz_o_que_fazer(monkeypatch, tmp_path):
    monkeypatch.delenv(ia.VARIAVEL_FALSA, raising=False)
    monkeypatch.delenv(ia.VARIAVEL_DA_CHAVE, raising=False)
    with pytest.raises(voz_pronta.SemVoz, match="chave do Gemini"):
        voz_pronta.narrar("gemini:Orus", ROTEIRO, tmp_path / "n.wav")


def test_a_ia_falsa_narra_sem_rede(tmp_path):
    n = voz_pronta.narrar("gemini:Puck", ROTEIRO, tmp_path / "n.wav")
    assert n.segundos > 3 and voz_pronta.usadas_hoje() == 0


def test_a_voz_local_falsa(tmp_path):
    n = voz_pronta.narrar("local:faber", ROTEIRO, tmp_path / "n.wav")
    assert n.aparelho == "falso" and n.pedacos == 3 and n.segundos > 3
    # as frases ficam guardadas: a segunda vez não sintetiza nada
    n2 = voz_pronta.narrar("local:faber", ROTEIRO, tmp_path / "n2.wav")
    assert n2.reaproveitados == 3 and n2.aparelho == "guardado"


def test_a_leitura_da_voz_local():
    assert voz_local.para_ler("Custa R$ 170 milhões.") == "Custa 170 milhões de reais."
    assert voz_local.para_ler("R$ 3,5 mil por mês") == "3,5 mil reais por mês"
    assert voz_local.para_ler("subiu 30% e US$ 20") == "subiu 30 por cento e 20 dólares"
    assert voz_local.para_ler("a 120 km/h e 35 °C") == "a 120 quilômetros por hora e 35 graus"


def test_a_instalacao_da_voz_local(monkeypatch):
    # sem o uv, o venv e o pip do Python do editor; com ele, o uv
    monkeypatch.setattr(voz_local.motor_de_voz, "achar_uv", lambda: None)
    sem_uv = voz_local.comandos()
    assert sem_uv[0][0] == "ambiente" and voz_local.PACOTE in sem_uv[1][1]
    monkeypatch.setattr(voz_local.motor_de_voz, "achar_uv", lambda: "/bin/uv")
    com_uv = voz_local.comandos()
    assert com_uv[0][1][:2] == ["/bin/uv", "venv"] and com_uv[1][1][-1] == voz_local.PACOTE
    e = voz_local.estado()
    assert e["instalado"] and e["espaco"] == voz_local.ESPACO     # a falsa conta como instalada


def test_a_pronuncia_vale_para_a_voz_pronta(tmp_path):
    n = voz_pronta.narrar("local:faber", "O GTA saiu.", tmp_path / "n.wav",
                          pronuncia={"GTA": "gê tê á"})
    assert n.pedacos == 1
    guardadas = sorted(voz_clonada.pasta_das_narracoes().glob("local-*.wav"))
    assert guardadas
