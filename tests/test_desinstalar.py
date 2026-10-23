"""
``editai --desinstalar``: o que sai sempre, o que é perguntado à parte (os modelos, na pasta
compartilhada do Hugging Face, e os vídeos editados), o "sim" que confirma e o programa, que
sai por último pelo ``uv``. Todas as pastas apontam para o ``tmp_path``: nada de verdade é
apagado, e o ``uv`` de verdade nunca é chamado.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from editor import cli, desinstalar, motor_de_voz


def _arquivo(caminho: Path, n: int = 1000) -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(b"x" * n)
    return caminho


@pytest.fixture
def maquina(tmp_path, monkeypatch):
    """Um computador com o Editai usado, no jeito do macOS (os dados e a configuração na mesma
    pasta): o motor, uma voz, a chave do Gemini, os temporários, os modelos (e um de outro
    programa, que nunca sai) e os vídeos."""
    dados = tmp_path / "Application Support" / "editor-de-video"
    cache = tmp_path / "Caches" / "editor-de-video"
    hf = tmp_path / "huggingface" / "hub"
    videos = tmp_path / "Movies" / "editor-de-video"
    _arquivo(dados / "motor-de-voz" / "modelo" / "pesos.bin", 5000)
    _arquivo(dados / "vozes" / "lucas" / "referencia.wav", 300)
    (dados / "config.json").write_text(json.dumps({"gemini_api_key": "AIza-teste"}))
    _arquivo(cache / "transcricoes" / "t.json", 200)
    _arquivo(hf / "models--Systran--faster-whisper-small" / "blobs" / "m", 700)
    _arquivo(hf / "models--Xenova--modnet" / "blobs" / "m", 100)
    outro = _arquivo(hf / "models--outro--programa" / "blobs" / "m", 900)
    _arquivo(videos / "meu-video-editado.mp4", 800)
    monkeypatch.setattr(desinstalar, "pastas_do_sistema",
                        lambda: {"dados": dados, "configuracao": dados, "temporarios": cache})
    monkeypatch.setattr(desinstalar, "pasta_dos_videos", lambda: videos)
    monkeypatch.setattr(desinstalar, "cache_do_hugging_face", lambda: hf)
    monkeypatch.setattr(desinstalar, "achar_uv", lambda: None)
    # o atalho também vai para o tmp: o Editai.app de verdade nunca entra num teste
    app = tmp_path / "Applications" / "Editai.app"
    _arquivo(app / "Contents" / "Info.plist", 50)
    monkeypatch.setattr(desinstalar, "caminhos_dos_atalhos", lambda: [app])
    return {"dados": dados, "cache": cache, "hf": hf, "videos": videos, "outro": outro, "app": app}


def _respostas(*r: str):
    fila = list(r)
    perguntas: list[str] = []

    def perguntar(texto: str) -> str:
        perguntas.append(texto)
        return fila.pop(0)

    perguntar.perguntas = perguntas  # type: ignore[attr-defined]
    return perguntar


class TestTudo:
    def test_mostra_tudo_e_sem_o_sim_nada_sai(self, maquina):
        saida: list[str] = []
        perguntar = _respostas("", "", "nao")
        assert desinstalar.tudo(perguntar=perguntar, escrever=saida.append) == 1
        texto = "\n".join(saida)
        assert "5,0 KB  o motor da voz sintetizada" in texto
        assert "as vozes gravadas" in texto and "as chaves do Gemini e do Pexels" in texto
        assert "os temporários" in texto and "Nada foi apagado." in texto
        # os modelos e os vídeos, perguntados à parte, antes do "sim"
        assert [p.split("(")[0] for p in perguntar.perguntas[:2]] == [
            "Apagar também os modelos de transcrição e de recorte, na pasta do Hugging Face, que "
            "outros programas também podem usar ", "Apagar também os vídeos editados "]
        assert 'Digite "sim"' in perguntar.perguntas[2]
        assert all(p.exists() for p in maquina.values())

    def test_apaga_o_do_editai_e_os_extras_ficam_no_enter(self, maquina):
        saida: list[str] = []
        assert desinstalar.tudo(perguntar=_respostas("", "", "sim"), escrever=saida.append) == 0
        assert not maquina["dados"].exists() and not maquina["cache"].exists()
        assert not maquina["app"].exists()
        assert "  apagado: o atalho Editai" in saida
        assert (maquina["hf"] / "models--Systran--faster-whisper-small").exists()
        assert maquina["videos"].exists() and maquina["outro"].exists()
        # a chave saiu do computador, mas continua valendo no Google
        assert any("aistudio.google.com/apikey" in s for s in saida)
        assert "Pronto: o Editai saiu deste computador." in saida

    def test_os_modelos_e_os_videos_quando_a_pessoa_diz_sim(self, maquina):
        responder = _respostas("s", "sim", "sim")
        assert desinstalar.tudo(perguntar=responder, escrever=lambda _s: None) == 0
        assert not (maquina["hf"] / "models--Systran--faster-whisper-small").exists()
        assert not (maquina["hf"] / "models--Xenova--modnet").exists()
        assert not maquina["videos"].exists()
        assert maquina["outro"].exists()                        # o modelo de outro programa fica

    def test_com_sim_nada_e_perguntado_e_os_extras_so_com_as_opcoes(self, maquina):
        def nunca(_texto):
            raise AssertionError("não era para perguntar")

        saida: list[str] = []
        assert desinstalar.tudo(sim=True, perguntar=nunca, escrever=saida.append) == 0
        assert not maquina["dados"].exists()
        assert maquina["videos"].exists() and (maquina["hf"] / "models--Xenova--modnet").exists()
        assert any("--com-modelos" in s for s in saida) and any("--com-videos" in s for s in saida)
        assert desinstalar.tudo(sim=True, com_videos=True, com_modelos=True, perguntar=nunca,
                                escrever=lambda _s: None) == 0
        assert not maquina["videos"].exists()
        assert not (maquina["hf"] / "models--Xenova--modnet").exists() and maquina["outro"].exists()

    def test_sem_nada_guardado(self, maquina):
        desinstalar.tudo(sim=True, com_videos=True, com_modelos=True, escrever=lambda _s: None)
        saida: list[str] = []
        assert desinstalar.tudo(perguntar=_respostas(), escrever=saida.append) == 0
        assert saida == ["O Editai não guardou nada neste computador."]

    def test_no_windows_o_cache_dentro_dos_dados_aparece_uma_vez(self, tmp_path, monkeypatch):
        dados = tmp_path / "AppData" / "Local" / "editor-de-video"
        _arquivo(dados / "Cache" / "envios" / "v.mp4", 400)
        _arquivo(dados / "presets.json", 50)
        monkeypatch.setattr(desinstalar, "pastas_do_sistema", lambda: {
            "dados": dados, "configuracao": dados, "temporarios": dados / "Cache"})
        itens = desinstalar.principais()
        assert [i.caminho for i in itens] == [dados]
        assert itens[0].bytes == 450
        assert itens[0].rotulo.endswith("as chaves do Gemini e do Pexels e os temporários "
                                         "(envios, transcrições, narrações e imagens)")


class TestOPrograma:
    @pytest.fixture
    def uv(self, maquina, tmp_path, monkeypatch):
        ferramentas = tmp_path / "uv-tools"
        _arquivo(ferramentas / "editai" / "bin" / "python", 600)
        chamadas: list[list[str]] = []

        def rodar(cmd, **_k):
            chamadas.append(list(cmd))
            if cmd[1:] == ["tool", "dir"]:
                return subprocess.CompletedProcess(cmd, 0, f"{ferramentas}\n", "")
            # o programa só sai depois dos dados
            assert not maquina["dados"].exists()
            return subprocess.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr(desinstalar, "achar_uv", lambda: "/bin/uv-falso")
        monkeypatch.setattr(desinstalar.subprocess, "run", rodar)
        return chamadas

    def test_sai_por_ultimo_pelo_uv(self, uv, monkeypatch):
        monkeypatch.setattr(sys, "platform", "darwin")
        saida: list[str] = []
        assert desinstalar.tudo(sim=True, escrever=saida.append) == 0
        assert uv[-1] == ["/bin/uv-falso", "tool", "uninstall", "editai"]
        assert "  apagado: o programa (os comandos editai e editar)" in saida
        assert any("600 bytes  o programa" in s for s in saida)

    def test_no_windows_mostra_o_comando(self, uv, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        saida: list[str] = []
        assert desinstalar.tudo(sim=True, escrever=saida.append) == 0
        assert ["/bin/uv-falso", "tool", "uninstall", "editai"] not in uv
        assert "Para terminar, feche o Editai e rode: uv tool uninstall editai" in saida


class TestSoOMotor:
    def test_pergunta_e_as_vozes_ficam(self):
        _arquivo(motor_de_voz.pasta() / "modelo" / "pesos.bin", 3000)
        voz = _arquivo(motor_de_voz.pasta().parent / "vozes" / "lucas" / "referencia.wav")
        saida: list[str] = []
        assert desinstalar.so_o_motor(perguntar=_respostas(""), escrever=saida.append) == 1
        assert motor_de_voz.pasta().exists()
        assert desinstalar.so_o_motor(perguntar=_respostas("s"), escrever=saida.append) == 0
        assert not motor_de_voz.pasta().exists() and voz.exists()
        assert saida[-1] == "Pronto: 3,0 KB liberados."

    def test_o_estado_diz_quanto_ocupa_de_verdade(self):
        assert motor_de_voz.estado()["ocupa"] == ""            # o falso, sem pasta
        _arquivo(motor_de_voz.pasta() / "modelo" / "pesos.bin", 8_400_000)
        assert motor_de_voz.estado()["ocupa"] == "8,4 MB"


def test_os_tamanhos_como_o_finder():
    assert [desinstalar.legivel(n) for n in (0, 552_000, 114_000_000, 8_400_000_000)] == [
        "0 bytes", "552 KB", "114 MB", "8,4 GB"]


def test_os_modelos_do_editai_sao_os_que_ele_baixa():
    assert desinstalar.repositorios_dos_modelos() == [
        "Systran/faster-whisper-tiny", "Systran/faster-whisper-base",
        "Systran/faster-whisper-small", "Systran/faster-whisper-medium", "Xenova/modnet"]


def test_pela_linha_de_comando(maquina):
    assert cli.main(["--desinstalar", "--sim"]) == 0
    assert not maquina["dados"].exists() and maquina["videos"].exists()
    assert cli.main(["--desinstalar-voz", "--sim"]) == 0       # já não há motor: nada a fazer
