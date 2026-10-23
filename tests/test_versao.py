"""
As versões: o aviso de versão nova (uma vez por dia, desligável, sem rede nos testes), o
``editai --atualizar``, o atalho que o instalador cria e os anexos de cada versão
(``instalador/montar.py`` e ``nova_versao.py``).
"""
from __future__ import annotations

import plistlib
import re
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

import httpx
import pytest

from editor import __version__, atalho, servidor, versao

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "instalador"))
import montar  # noqa: E402
import nova_versao  # noqa: E402


@pytest.fixture
def github(monkeypatch):
    """O GitHub de mentira: conta os pedidos e responde a última versão que o teste mandar."""
    estado = {"pedidos": 0, "tag": "v9.0.0", "codigo": 200}

    def responder(pedido: httpx.Request) -> httpx.Response:
        estado["pedidos"] += 1
        assert str(pedido.url) == versao.API
        assert pedido.headers["user-agent"] == f"Editai/{__version__}"
        return httpx.Response(estado["codigo"], json={
            "tag_name": estado["tag"], "html_url": f"https://github.com/x/{estado['tag']}",
            "published_at": "2026-10-30T12:00:00Z"})

    monkeypatch.delenv(versao.VARIAVEL_FALSA)
    monkeypatch.setattr(versao, "_transporte", httpx.MockTransport(responder))
    return estado


class TestOAviso:
    def test_avisa_e_pergunta_uma_vez_por_dia(self, github):
        a = versao.aviso(agora=1000.0)
        assert (a["atual"], a["nova"], a["data"]) == (__version__, "9.0.0", "2026-10-30")
        assert a["endereco"] == "https://github.com/x/v9.0.0"
        versao.aviso(agora=1000.0 + 23 * 3600)
        assert github["pedidos"] == 1                          # o mesmo dia: a guardada
        versao.aviso(agora=1000.0 + 25 * 3600)
        assert github["pedidos"] == 2

    def test_sem_aviso_quando_nao_ha_versao_mais_nova(self, github):
        github["tag"] = f"v{__version__}"
        assert versao.aviso() is None
        github["tag"] = "v99.0.0-beta"                          # prévia não avisa
        assert versao.aviso(forcar=True) is None

    def test_sem_internet_abre_igual_e_tenta_de_novo_em_uma_hora(self, github, monkeypatch):
        def cair(_pedido):
            raise httpx.ConnectError("sem rede")

        monkeypatch.setattr(versao, "_transporte", httpx.MockTransport(cair))
        assert versao.aviso(agora=0.0) is None
        monkeypatch.setattr(versao, "_transporte", httpx.MockTransport(
            lambda p: httpx.Response(200, json={"tag_name": "v9.0.0", "html_url": "u"})))
        assert versao.aviso(agora=30 * 60.0) is None           # meia hora depois: espera
        assert versao.aviso(agora=61 * 60.0)["nova"] == "9.0.0"

    def test_nao_avisar_mais(self, github, monkeypatch):
        versao.silenciar()
        assert versao.aviso() is None and github["pedidos"] == 0
        (versao._arquivo()).unlink()
        monkeypatch.setenv(versao.VARIAVEL_DESLIGA, "1")
        assert versao.aviso() is None

    def test_os_testes_nunca_vao_ao_github(self):
        assert versao.ultima(forcar=True) is None

    def test_pela_pagina(self, github, tmp_path):
        from fastapi.testclient import TestClient

        app = servidor.criar_app("t", porta=8898, pasta_saida=tmp_path / "saida")
        cabeca = {"X-Editor-Token": "t"}
        with TestClient(app, base_url="http://127.0.0.1:8898") as cliente:
            r = cliente.get("/api/versao", headers=cabeca).json()
            assert r["atual"] == __version__ and r["aviso"]["nova"] == "9.0.0"
            assert cliente.post("/api/versao/silenciar", headers=cabeca).json()["aviso"] is None
            assert cliente.get("/api/versao", headers=cabeca).json()["aviso"] is None


class TestAtualizar:
    def test_instala_a_nova_pelo_uv(self, github, monkeypatch):
        monkeypatch.setattr(sys, "platform", "darwin")
        monkeypatch.setattr("editor.motor_de_voz.achar_uv", lambda: "/bin/uv")
        monkeypatch.setattr(atalho, "caminhos", lambda *_a: [])
        chamadas = []
        saida: list[str] = []

        def rodar(cmd, **_k):
            chamadas.append(cmd)
            return subprocess.CompletedProcess(cmd, 0)

        assert versao.atualizar(escrever=saida.append, rodar=rodar) == 0
        assert chamadas == [["/bin/uv", "tool", "install", "--force", "--python", "3.12",
                             "https://github.com/lucasteles1231/editai/releases/download/v9.0.0/"
                             "editai-9.0.0-py3-none-any.whl"]]
        assert saida[-1].startswith("Pronto: o Editai 9.0.0 está instalado.")

    def test_no_windows_mostra_o_comando(self, github, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        saida: list[str] = []
        assert versao.atualizar(escrever=saida.append, rodar=None) == 0
        assert "irm https://lucasteles1231.github.io/editai/instalar.ps1 | iex" in saida[-1]

    def test_ja_na_mais_nova(self, github):
        github["tag"] = f"v{__version__}"
        saida: list[str] = []
        assert versao.atualizar(escrever=saida.append, rodar=None) == 0
        assert saida == [f"Você já tem a versão mais nova ({__version__})."]


class TestOAtalho:
    @pytest.fixture
    def casa(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        editai = tmp_path / "bin" / "editai"
        editai.parent.mkdir()
        editai.write_text("#!/bin/sh\n")
        monkeypatch.setattr(sys, "argv", [str(editai), "--criar-atalho"])
        return tmp_path, editai

    def test_macos(self, casa):
        home, editai = casa
        (app,) = atalho.criar("darwin")
        assert app == home / "Applications" / "Editai.app"
        info = plistlib.loads((app / "Contents" / "Info.plist").read_bytes())
        assert info["CFBundleExecutable"] == "abrir"
        assert info["CFBundleShortVersionString"] == __version__
        abrir = app / "Contents" / "MacOS" / "abrir"
        assert abrir.read_text() == f'#!/bin/sh\nexec open -a Terminal "{editai}"\n'
        assert abrir.stat().st_mode & 0o111
        assert (app / "Contents" / "Resources" / "editai.icns").read_bytes()[:4] == b"icns"

    def test_linux(self, casa):
        home, editai = casa
        (desktop,) = atalho.criar("linux")
        texto = desktop.read_text()
        assert desktop == home / ".local" / "share" / "applications" / "editai.desktop"
        assert f'Exec="{editai}"' in texto and "Terminal=true" in texto

    def test_windows_pelo_powershell(self, casa, monkeypatch):
        home, editai = casa
        feitos = []

        def rodar(cmd, **k):
            if "GetFolderPath" in cmd[-1]:
                return subprocess.CompletedProcess(cmd, 0, f"{home}\\Menu\n{home}\\Desktop\n", "")
            feitos.append(k["env"]["EDITAI_LNK"])
            assert k["env"]["EDITAI_ALVO"] == str(editai)
            assert k["env"]["EDITAI_ICONE"].endswith("editai.ico")
            return subprocess.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr(atalho.subprocess, "run", rodar)
        atalho.criar("win32")
        assert [Path(f).name for f in feitos] == ["Editai.lnk", "Editai.lnk"]

    def test_o_editai_que_roda_ganha_do_path(self, casa, monkeypatch):
        _home, editai = casa
        monkeypatch.setattr(atalho.shutil, "which", lambda _n: "/usr/local/bin/editai")
        assert atalho.executavel() == editai


class TestOsAnexos:
    def test_uma_versao_inteira(self, tmp_path):
        assert montar.main([str(tmp_path / "anexos"), "--versao", "0.2.0"]) == 0
        nomes = sorted(p.name for p in (tmp_path / "anexos").iterdir())
        assert nomes == ["Instalar-Editai-Windows.cmd", "Instalar-Editai-macOS.zip",
                         "SHA256SUMS.txt", "instalar.ps1", "instalar.sh"]
        sh = (tmp_path / "anexos" / "instalar.sh").read_text()
        assert 'VERSAO="${EDITAI_VERSAO:-0.2.0}"' in sh and "__VERSAO__" not in sh
        ps1 = (tmp_path / "anexos" / "instalar.ps1").read_bytes()
        assert b"'0.2.0'" in ps1 and b"\r\n" in ps1 and ps1.isascii()
        with zipfile.ZipFile(tmp_path / "anexos" / "Instalar-Editai-macOS.zip") as z:
            (info,) = z.infolist()
            assert info.filename == "Instalar Editai.command" and (info.external_attr >> 16) & 0o111
        cmd = (tmp_path / "anexos" / "Instalar-Editai-Windows.cmd").read_text()
        assert "releases/download/v0.2.0/instalar.ps1" in cmd
        somas = (tmp_path / "anexos" / "SHA256SUMS.txt").read_text().splitlines()
        assert len(somas) == 4 and all(re.fullmatch(r"[0-9a-f]{64}  \S.*", s) for s in somas)
        assert "### Novidades" in (tmp_path / "notas.md").read_text()

    def test_a_tag_precisa_bater(self):
        montar.conferir(f"v{__version__}")                     # o CHANGELOG tem a seção dela
        with pytest.raises(SystemExit, match="não é a versão"):
            montar.conferir("v99.0.0")

    def test_a_versao_e_uma_so(self):
        projeto = tomllib.loads((RAIZ / "pyproject.toml").read_text())["project"]["version"]
        assert projeto == __version__
        assert "__VERSAO__" in (RAIZ / "instalador" / "instalar.sh").read_text()
        assert "__VERSAO__" in (RAIZ / "instalador" / "instalar.ps1").read_text()

    def test_nova_versao(self, tmp_path, monkeypatch):
        for nome in ("pyproject.toml", "CHANGELOG.md"):
            (tmp_path / nome).write_text((RAIZ / nome).read_text())
        (tmp_path / "editor").mkdir()
        init = (RAIZ / "editor" / "__init__.py").read_text()
        (tmp_path / "editor" / "__init__.py").write_text(init)
        monkeypatch.setattr(nova_versao, "RAIZ", tmp_path)
        with pytest.raises(SystemExit, match="escreva antes"):
            nova_versao.main(["7.7.7"])
        assert nova_versao.main(["0.2.0"]) == 0
        assert 'version = "0.2.0"' in (tmp_path / "pyproject.toml").read_text()
        assert '__version__ = "0.2.0"' in (tmp_path / "editor" / "__init__.py").read_text()
        changelog = (tmp_path / "CHANGELOG.md").read_text()
        assert re.search(r"^## \[0\.2\.0\] — \d\d/\d\d/\d{4}$", changelog, re.M)


def test_o_instalador_sh_e_valido():
    r = subprocess.run(["sh", "-n", str(RAIZ / "instalador" / "instalar.sh")], capture_output=True)
    assert r.returncode == 0, r.stderr


def test_o_aviso_da_versao_na_privacidade():
    """Todo acesso à rede está na seção de privacidade, e o aviso de versão é um."""
    texto = (RAIZ / "docs" / "guia" / "seguranca-e-privacidade.md").read_text(encoding="utf-8")
    assert "api.github.com" in texto and versao.VARIAVEL_DESLIGA in texto

