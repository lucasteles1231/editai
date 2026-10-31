"""
O roteiro pelo tema (editor/escrita.py): o pedido, a conferência do tamanho e do gancho, o
conserto de uma vez, a IA falsa e o caminho sem a chave. O Gemini é um transporte falso do
httpx, como em ``test_roteiro.py``.
"""
from __future__ import annotations

import json

import httpx
import pytest

from editor import escrita, ia

CHAVE = "AIzaSyTESTE-chave-de-mentira-123456"


@pytest.fixture
def de_verdade(monkeypatch):
    monkeypatch.delenv(ia.VARIAVEL_FALSA, raising=False)
    monkeypatch.setenv(ia.VARIAVEL_DA_CHAVE, CHAVE)


def _resposta(dados: dict) -> httpx.Response:
    texto = json.dumps(dados, ensure_ascii=False)
    return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": texto}]},
                                                     "finishReason": "STOP"}]})


class _Gemini:
    def __init__(self, *respostas: httpx.Response):
        self.fila = list(respostas)
        self.pedidos: list[dict] = []

    def __call__(self, pedido: httpx.Request) -> httpx.Response:
        self.pedidos.append(json.loads(pedido.content))
        return self.fila.pop(0)

    def texto(self, k: int) -> str:
        return " ".join(p["text"] for c in self.pedidos[k]["contents"] for p in c["parts"]
                        if "text" in p)

    @property
    def transporte(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)


RESTO = ("A luz do sol mistura todas as cores e o ar espalha mais o azul que o vermelho por "
         "isso a gente vê o céu assim")


def _paragrafos(palavras: int, comeco: str = "Por que o céu é azul de dia?") -> list[str]:
    resto = RESTO.split()
    texto = comeco.split()
    while len(texto) < palavras:
        texto += resto
    texto = texto[:palavras]
    return [" ".join(texto[k:k + 20]) for k in range(0, len(texto), 20)]


def test_o_tamanho_sai_do_tempo():
    assert escrita.palavras_alvo(45) == 117
    assert escrita.palavras_alvo(1) == escrita.palavras_alvo(escrita.SEGUNDOS_MINIMOS)
    assert escrita.palavras_alvo(10_000) == escrita.palavras_alvo(escrita.SEGUNDOS_MAXIMOS)


def test_escreve_num_pedido_so(de_verdade):
    gemini = _Gemini(_resposta({"titulo": "Por que o céu é azul.",
                                "paragrafos": _paragrafos(115)}))
    r = escrita.escrever("por que o céu é azul", 45, transporte=gemini.transporte)
    assert len(gemini.pedidos) == 1 and r.pedidos == 1 and r.por == "gemini"
    assert r.titulo == "Por que o céu é azul"            # sem o ponto final
    assert "\n\n" in r.texto and r.palavras == 115
    pedido = gemini.texto(0)
    assert "por que o céu é azul" in pedido and "117 palavras" in pedido
    assert "você sabia" in pedido.lower()                 # a regra do gancho vai no pedido


def test_curto_demais_volta_para_o_conserto(de_verdade):
    gemini = _Gemini(_resposta({"titulo": "Céu", "paragrafos": _paragrafos(40)}),
                     _resposta({"titulo": "Céu azul", "paragrafos": _paragrafos(118)}))
    r = escrita.escrever("por que o céu é azul", 45, transporte=gemini.transporte)
    assert len(gemini.pedidos) == 2 and r.pedidos == 2
    assert "40 palavras" in gemini.texto(1) and r.palavras == 118 and r.titulo == "Céu azul"


def test_o_gancho_gasto_volta_para_o_conserto(de_verdade):
    ruim = _paragrafos(117, comeco="Você sabia que o céu é azul por causa do ar?")
    gemini = _Gemini(_resposta({"titulo": "Céu", "paragrafos": ruim}),
                     _resposta({"titulo": "Céu", "paragrafos": _paragrafos(117)}))
    r = escrita.escrever("céu azul", 45, transporte=gemini.transporte)
    assert 'começa com "você sabia"' in gemini.texto(1)
    assert r.paragrafos[0].startswith("Por que")


def test_o_conserto_pior_nao_troca_o_primeiro(de_verdade):
    gemini = _Gemini(_resposta({"titulo": "Céu", "paragrafos": _paragrafos(60)}),
                     _resposta({"titulo": "", "paragrafos": []}))
    r = escrita.escrever("céu azul", 45, transporte=gemini.transporte)
    assert r.palavras == 60                                # o primeiro, que tinha texto


def test_sem_a_chave_diz_o_que_fazer(monkeypatch):
    monkeypatch.delenv(ia.VARIAVEL_FALSA, raising=False)
    monkeypatch.delenv(ia.VARIAVEL_DA_CHAVE, raising=False)
    with pytest.raises(escrita.SemRoteiro, match="IA local ou cole a chave do Gemini"):
        escrita.escrever("céu azul")
    with pytest.raises(escrita.SemRoteiro, match="tema"):
        escrita.escrever("   ")


def test_o_erro_do_gemini_vira_mensagem(de_verdade):
    gemini = _Gemini(httpx.Response(429, json={"error": {"message": "quota", "status":
                                                         "RESOURCE_EXHAUSTED"}}),
                     *[httpx.Response(429, json={"error": {"message": "quota",
                                                           "status": "RESOURCE_EXHAUSTED"}})
                       for _ in range(6)])
    with pytest.raises(escrita.SemRoteiro, match="cota"):
        escrita.escrever("céu azul", transporte=gemini.transporte)


def test_no_auto_o_tamanho_e_o_que_o_assunto_pede():
    """Sem tempo pedido (o Auto), o roteiro sai no tamanho do assunto, até o teto da
    plataforma: passou, volta para o conserto; curto demais também."""
    pedido = escrita.montar_pedido("Por que o céu é azul", None, teto=180)
    assert "no tamanho que o assunto pede" in pedido and "de 30 a 60 s" in pedido
    assert f"Nunca passe de {escrita.palavras_alvo(180)} palavras" in pedido
    longo = {"titulo": "x", "paragrafos": ["palavra " * 500]}
    assert "passa do limite" in escrita.conferir(longo, None, teto=60)[1][0]
    curto = {"titulo": "x", "paragrafos": ["Uma frase só."]}
    assert "curto demais" in escrita.conferir(curto, None, teto=180)[1][0]
    assert not escrita.conferir({"titulo": "x", "paragrafos": ["palavra " * 100]}, None,
                                teto=180)[1]
    assert escrita.escrever("O céu azul", None, teto=180).por == "falsa"


def test_a_ia_falsa_escreve_do_tamanho_pedido():
    r = escrita.escrever("Como o freio ABS funciona", 30)
    assert r.por == "falsa" and r.titulo == "Como o freio ABS funciona"
    assert r.palavras >= escrita.palavras_alvo(30) * 0.9
    assert r.paragrafos[0].startswith("Por que como o freio abs funciona")


def test_o_video_so_pelo_tema_no_terminal(tmp_path, monkeypatch, capsys):
    """``editai --tema "..."``: escreve, narra (a voz local falsa), acha as fotos (falsas) e
    monta o vídeo, com a pasta das fotos, o roteiro e os créditos ao lado."""
    from editor import cli, servidor, video

    monkeypatch.setattr(servidor, "pasta_de_saida_padrao", lambda: tmp_path / "videos")
    destino = tmp_path / "saiu.mp4"
    codigo = cli.main(["--tema", "Como o freio ABS funciona", "--duracao", "15",
                       "--narrador", "local", "-o", str(destino), "--previa", "4"])
    assert codigo == 0, capsys.readouterr().err
    pasta = tmp_path / "videos" / "fotos" / "como-o-freio-abs-funciona"
    assert (pasta / "roteiro.txt").read_text(encoding="utf-8").startswith("Por que")
    assert (pasta / "narracao.wav").is_file() and (pasta / "creditos.txt").is_file()
    info = video.sondar(destino)
    assert info.vertical and info.tem_audio
    saida = capsys.readouterr().out
    assert "escrevendo o roteiro" in saida and "fotos em" in saida
