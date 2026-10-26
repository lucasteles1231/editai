"""
O auditor das imagens (editor/auditor.py): a nota pelo modelo, com as sessões do onnxruntime e
o vocabulário imitados; a escolha (o piso, a ordem e as repetidas); o download conferido pelo
SHA-256; e o auditor falso dos testes. O modelo de verdade roda em ``auditor_de_verdade.py``.
"""
from __future__ import annotations

import hashlib

import numpy as np
import pytest
from PIL import Image

from editor import auditor


@pytest.fixture
def de_verdade(monkeypatch):
    monkeypatch.delenv(auditor.VARIAVEL_FALSA, raising=False)
    monkeypatch.setattr(auditor, "_sessoes", {})
    monkeypatch.setattr(auditor, "_textos", {})
    monkeypatch.setattr(auditor, "_vocabulario", None)
    monkeypatch.setattr(auditor, "PROCESSO_A_PARTE", False)     # as imitações ficam aqui


class _Sessao:
    """Uma sessão do onnxruntime imitada: devolve o que ``saida`` calcular das entradas."""

    def __init__(self, saida):
        self.saida = saida
        self.entradas: list[dict] = []

    def run(self, _nomes, entradas):
        self.entradas.append(entradas)
        return [self.saida(entradas)]


class _Vocabulario:
    def __init__(self):
        self.textos: list[str] = []

    def encode(self, texto):
        self.textos.append(texto)
        return type("Codificado", (), {"ids": [7] * auditor.TOKENS})()


def _cor(rgb) -> Image.Image:
    return Image.new("RGB", (320, 180), rgb)


def test_a_nota_e_o_cosseno_entre_a_imagem_e_o_texto(de_verdade, monkeypatch):
    # o "modelo": o vetor da imagem é a cor média dela, e o do texto aponta para o vermelho
    imagem = _Sessao(lambda e: e["pixel_values"].mean(axis=(2, 3)) + 1.0)
    texto = _Sessao(lambda e: np.array([[2.0, 0.0, 0.0]] * len(e["input_ids"])))
    vocabulario = _Vocabulario()
    monkeypatch.setattr(auditor, "_arquivo", lambda nome: nome)
    monkeypatch.setattr(auditor, "_vocabulario", vocabulario)
    abertas: list[str] = []

    def sessao(nome):
        abertas.append(nome)
        auditor._sessoes[nome] = imagem if nome == auditor.IMAGEM else texto
        return auditor._sessoes[nome]

    monkeypatch.setattr(auditor, "_sessao", sessao)
    vermelho, azul, verde = _cor((255, 0, 0)), _cor((0, 0, 255)), _cor((0, 255, 0))
    n = auditor.avaliar([vermelho, azul, verde], "  Um Céu\nVERMELHO ")
    assert n.notas == [1.0, 0.0, 0.0]
    assert np.allclose(np.linalg.norm(n.vetores, axis=1), 1.0)
    # o SigLIP 2 foi treinado com o texto em minúsculas
    assert vocabulario.textos == ["um céu vermelho"]
    # as imagens vão aos pares (o pico de memória cai à metade), e o texto, uma vez só
    assert [e["pixel_values"].shape[0] for e in imagem.entradas] == [2, 1]
    pixels = imagem.entradas[0]["pixel_values"]
    assert pixels.shape[1:] == (3, auditor.LADO, auditor.LADO) and pixels.dtype == np.float32
    assert pixels.min() >= -1.0 and pixels.max() <= 1.0
    ids = texto.entradas[0]["input_ids"]
    assert ids.shape == (1, auditor.TOKENS) and ids.dtype == np.int64
    # a parte do texto fecha logo depois (aberta, ela ocupa uns 710 MB)
    assert auditor.TEXTO not in auditor._sessoes and auditor.IMAGEM in auditor._sessoes
    auditor.avaliar([vermelho], "  Um Céu\nVERMELHO ")
    assert abertas.count(auditor.TEXTO) == 1          # o vetor do texto ficou guardado


def test_os_textos_do_video_saem_de_uma_vez(de_verdade, monkeypatch):
    texto = _Sessao(lambda e: np.ones((len(e["input_ids"]), 3)))
    monkeypatch.setattr(auditor, "_arquivo", lambda nome: nome)
    monkeypatch.setattr(auditor, "_vocabulario", _Vocabulario())
    monkeypatch.setattr(auditor, "_sessao", lambda nome: auditor._sessoes.setdefault(nome, texto))
    assert auditor.preparar([f"trecho {k}" for k in range(20)] + ["trecho 0"])
    assert [len(e["input_ids"]) for e in texto.entradas] == [16, 4]
    assert len(auditor._textos) == 20


def test_a_escolha_pelo_piso_pela_nota_e_sem_repetidas():
    vetores = np.eye(4, dtype=np.float32)
    vetores[3] = vetores[1]                         # a 3 é a mesma cena da 1
    n = auditor.Notas([0.12, 0.15, 0.03, 0.14], vetores)
    assert auditor.escolher(n, 2) == [1, 0]         # a 3 repete a 1; a 2 fica abaixo do piso
    assert auditor.escolher(n, 9) == [1, 0]
    assert auditor.escolher(n, 1) == [1]
    # a cena já usada em outro trecho não volta, nem pela cópia
    assert auditor.escolher(n, 2, ja=[vetores[1]]) == [0]
    assert auditor.escolher(n, 3, piso=0.0) == [1, 0, 2]


def test_juntar_as_duas_levas():
    a = auditor.Notas([0.1], np.ones((1, 3), np.float32))
    vazio = auditor.avaliar([], "nada")
    assert auditor.juntar(vazio, a) is a and auditor.juntar(a, vazio) is a
    b = auditor.juntar(a, a)
    assert b.notas == [0.1, 0.1] and b.vetores.shape == (2, 3)


def test_o_auditor_falso_deixa_a_ordem_de_chegada():
    n = auditor.avaliar([_cor((0, 0, 0))] * 5, "qualquer coisa")
    assert auditor.escolher(n, 5) == [0, 1, 2, 3, 4]       # a mesma nota, nenhuma repetida
    outra = auditor.avaliar([_cor((0, 0, 0))] * 5, "outra")
    assert auditor.escolher(outra, 5, ja=list(n.vetores)) == [0, 1, 2, 3, 4]
    assert auditor.baixado() and auditor.preparar()


def test_os_arquivos_sao_os_int8():
    # o "*_quantized" da exportação é o uint8 da imagem, que errava o dobro (25/10/2026)
    assert set(auditor.ARQUIVOS) == {"onnx/vision_model_int8.onnx",
                                     "onnx/text_model_int8.onnx", "tokenizer.json"}
    assert all(len(sha) == 64 for sha in auditor.ARQUIVOS.values())


def test_o_arquivo_baixado_e_conferido(de_verdade, monkeypatch, tmp_path):
    import huggingface_hub

    bom, ruim = tmp_path / "bom.onnx", tmp_path / "ruim.onnx"
    bom.write_bytes(b"modelo")
    ruim.write_bytes(b"outro")
    pedidos = []

    def baixar(repo, nome, *, revision, local_files_only=False):
        pedidos.append((repo, nome, revision, local_files_only))
        if local_files_only:
            raise FileNotFoundError(nome)               # ainda não está no cache
        return str(bom if nome == "bom" else ruim)

    monkeypatch.setattr(huggingface_hub, "hf_hub_download", baixar)
    certo = hashlib.sha256(b"modelo").hexdigest()
    monkeypatch.setattr(auditor, "ARQUIVOS", {"bom": certo, "ruim": certo})
    assert not auditor.baixado()
    assert auditor._arquivo("bom") == bom
    assert pedidos[-1] == (auditor.REPOSITORIO, "bom", auditor.REVISAO, False)
    with pytest.raises(auditor.ErroDoAuditor, match="não confere"):
        auditor._arquivo("ruim")
    assert not ruim.exists()                # o arquivo errado sai, para baixar de novo


def test_sem_internet_na_primeira_vez_ele_so_avisa(de_verdade, monkeypatch, caplog):
    def sem_rede(nome):
        raise OSError("sem rede")

    monkeypatch.setattr(auditor, "_arquivo", sem_rede)
    assert auditor.preparar(["um trecho"]) is False
    assert "não carregou" in caplog.text


def test_soltar_devolve_a_memoria(de_verdade):
    auditor._sessoes[auditor.IMAGEM] = "sessão"
    auditor._textos["um trecho"] = np.ones(3)
    auditor.soltar()
    assert not auditor._sessoes and not auditor._textos and auditor._vocabulario is None
