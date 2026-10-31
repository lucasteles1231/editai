"""
A IA local (editor/ia_local.py): o pacote de cada sistema, a instalação com os downloads
conferidos pelo SHA-256 (a rede é um transporte falso do httpx, e o teste do servidor é
trocado), o pacote de reserva quando o primeiro não abre, o cancelamento, o pedido no
formato do llama-server e a desinstalação. O llama-server de verdade roda em
``ia_local_de_verdade.py``.
"""
from __future__ import annotations

import hashlib
import io
import json
import tarfile

import httpx
import pytest

from editor import ia_local

MODELO, PROJETOR = b"pesos do modelo" * 1000, b"pesos do projetor" * 100


def _pacote(nome: str) -> bytes:
    """Um .tar.gz com um llama-server de mentira dentro da pasta do release."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        dados = b"#!/bin/sh\necho llama\n"
        info = tarfile.TarInfo(f"{nome}/llama-server")
        info.size, info.mode = len(dados), 0o755
        t.addfile(info, io.BytesIO(dados))
    return buf.getvalue()


class _Rede:
    def __init__(self, arquivos: dict[str, bytes]):
        self.arquivos = arquivos
        self.pedidos: list[str] = []

    def __call__(self, pedido: httpx.Request) -> httpx.Response:
        nome = pedido.url.path.rsplit("/", 1)[-1]
        self.pedidos.append(nome)
        if nome not in self.arquivos:
            return httpx.Response(404)
        return httpx.Response(200, content=self.arquivos[nome])

    @property
    def transporte(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)


@pytest.fixture
def maquina(monkeypatch):
    """Um sistema com dois pacotes (o de placa e o de processador) e o modelo pequeno."""
    sha = lambda b: hashlib.sha256(b).hexdigest()  # noqa: E731
    placa, processador = _pacote("placa"), _pacote("processador")
    monkeypatch.setattr(ia_local, "sistema", lambda: ("linux", "x64"))
    monkeypatch.setattr(ia_local, "PACOTES", {("linux", "x64"): [
        ("placa.tar.gz", sha(placa)), ("processador.tar.gz", sha(processador))]})
    monkeypatch.setattr(ia_local, "ARQUIVOS", {ia_local.MODELO: sha(MODELO),
                                                ia_local.PROJETOR: sha(PROJETOR)})
    monkeypatch.setattr(ia_local.sys, "platform", "linux")
    testados: list[str] = []
    monkeypatch.setattr(ia_local, "_testar", lambda executavel: testados.append(
        executavel.parent.name))
    rede = _Rede({"placa.tar.gz": placa, "processador.tar.gz": processador,
                  ia_local.MODELO: MODELO, ia_local.PROJETOR: PROJETOR})
    return rede, testados


def test_o_pacote_de_cada_sistema(monkeypatch):
    for plataforma, maquina_, esperado in (("darwin", "arm64", ("darwin", "arm64")),
                                           ("darwin", "x86_64", ("darwin", "x64")),
                                           ("win32", "AMD64", ("win32", "x64")),
                                           ("linux", "aarch64", ("linux", "arm64")),
                                           ("linux", "x86_64", ("linux", "x64"))):
        monkeypatch.setattr(ia_local.sys, "platform", plataforma)
        monkeypatch.setattr(ia_local.platform, "machine", lambda m=maquina_: m)
        assert ia_local.sistema() == esperado
        assert esperado in ia_local.PACOTES
    # no Windows e no Linux, o de placa (Vulkan) vem antes do de processador
    for chave in (("win32", "x64"), ("linux", "x64")):
        assert "vulkan" in ia_local.PACOTES[chave][0][0]


def test_instala_conferindo_e_testa_o_pacote_da_placa(maquina):
    rede, testados = maquina
    registro = ia_local.instalar(transporte=rede.transporte)
    assert registro["pacote"] == "placa" and testados == ["placa"]
    assert ia_local.instalado() and ia_local.servidor().name == "llama-server"
    assert (ia_local.pasta() / "modelo" / ia_local.MODELO).read_bytes() == MODELO
    assert not (ia_local.pasta() / "pacotes").exists()       # o .tar.gz sai depois
    assert rede.pedidos == ["placa.tar.gz", ia_local.MODELO, ia_local.PROJETOR]
    e = ia_local.estado()
    assert e["instalado"] and not e["instalando"] and e["modelo"] == "Qwen3.5-4B"


def test_sem_abrir_na_placa_fica_o_do_processador(maquina, monkeypatch):
    rede, testados = maquina

    def testar(executavel):
        testados.append(executavel.parent.name)
        if executavel.parent.name == "placa":
            raise ia_local.ErroDaIALocal("o Vulkan não abriu")

    monkeypatch.setattr(ia_local, "_testar", testar)
    assert ia_local.instalar(transporte=rede.transporte)["pacote"] == "processador"
    assert testados == ["placa", "processador"]


def test_o_arquivo_que_nao_confere_e_recusado(maquina):
    rede, _ = maquina
    rede.arquivos[ia_local.MODELO] = b"outro modelo"
    with pytest.raises(ia_local.ErroDaIALocal, match="não confere"):
        ia_local.instalar(transporte=rede.transporte)
    modelo = ia_local.pasta() / "modelo"
    assert not (modelo / ia_local.MODELO).exists()
    assert not list(modelo.glob("*.parcial"))
    assert not ia_local.instalado() and "não confere" in ia_local.estado()["erro"]


def test_cancelar_no_meio(maquina):
    rede, _ = maquina

    def cancela_no_modelo(pedido):
        if pedido.url.path.endswith(ia_local.MODELO):
            ia_local.cancelar_instalacao()
        return rede(pedido)

    with pytest.raises(ia_local.ErroDaIALocal, match="cancelada"):
        ia_local.instalar(transporte=httpx.MockTransport(cancela_no_modelo))
    assert not ia_local.instalado()


def test_o_pedido_no_formato_do_llama_server():
    corpo = ia_local.corpo_json("o sistema", "o pedido", {"type": "object"}, [b"jpeg"], 0.3)
    conteudo = corpo["messages"][1]["content"]
    # as imagens antes do texto
    assert conteudo[0]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert conteudo[-1] == {"type": "text", "text": "o pedido"}
    assert corpo["response_format"]["json_schema"]["schema"] == {"type": "object"}
    assert corpo["chat_template_kwargs"] == {"enable_thinking": False}
    assert corpo["messages"][0] == {"role": "system", "content": "o sistema"}


def test_a_resposta_cortada_e_o_json_quebrado(monkeypatch):
    s = object.__new__(ia_local._Servidor)
    s.base, s.chave, s.ultimo = "http://127.0.0.1:1", "chave", 0.0
    respostas = iter([{"choices": [{"finish_reason": "stop",
                                    "message": {"content": json.dumps({"ok": "sim"})}}]},
                      {"choices": [{"finish_reason": "length", "message": {"content": "{"}}]},
                      {"choices": [{"finish_reason": "stop", "message": {"content": "{"}}]}])
    pedidos = []

    def post(url, json, timeout, headers):
        pedidos.append(headers["Authorization"])
        return httpx.Response(200, json=next(respostas))

    monkeypatch.setattr(httpx, "post", post)
    assert s.perguntar_json("s", "p", {}, [], 0.0) == {"ok": "sim"}
    assert pedidos == ["Bearer chave"]
    with pytest.raises(ia_local.ErroDaIALocal, match="cortada"):
        s.perguntar_json("s", "p", {}, [], 0.0)
    with pytest.raises(ia_local.ErroDaIALocal, match="quebrado"):
        s.perguntar_json("s", "p", {}, [], 0.0)


def test_sem_instalar_diz_o_que_fazer():
    with pytest.raises(ia_local.ErroDaIALocal, match="instalar-ia"):
        ia_local.perguntar_json("s", "p", {}, temperatura=0.0)


def test_desinstalar_apaga_a_pasta(maquina):
    rede, _ = maquina
    ia_local.instalar(transporte=rede.transporte)
    ia_local.desinstalar()
    assert not ia_local.pasta().exists() and not ia_local.instalado()
