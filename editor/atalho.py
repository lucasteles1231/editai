"""
O atalho "Editai" que o instalador cria (``editai --criar-atalho``), para abrir o editor sem
digitar nada:

- **macOS:** ``~/Applications/Editai.app``, que abre o Terminal rodando o ``editai``. Criado
  aqui, e não baixado, ele não passa pelo aviso do Gatekeeper (só o que vem da internet é
  marcado). Fechar a janela do Terminal fecha o Editai, como o Ctrl+C.
- **Windows:** ``Editai.lnk`` no menu Iniciar e na Área de Trabalho, apontando para o
  ``editai.exe``. A janela preta que abre junto é o Editai rodando; fechar ela fecha o Editai.
- **Linux:** ``~/.local/share/applications/editai.desktop``, com ``Terminal=true``: aparece no
  menu de aplicativos.

``editai --desinstalar`` apaga o que foi criado aqui (:func:`caminhos`).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from importlib.resources import files
from pathlib import Path

from editor import __version__

NOME = "Editai"
#: O identificador do app no macOS (o domínio do site, ao contrário).
IDENTIFICADOR = "io.github.lucasteles1231.editai"


class ErroDoAtalho(RuntimeError):
    pass


def _icone(extensao: str) -> Path:
    return Path(str(files("editor").joinpath("recursos", "icone", f"editai.{extensao}")))


def executavel() -> Path:
    """O comando ``editai`` que o atalho roda: o que está rodando agora (o instalador chama o
    recém-instalado pelo caminho inteiro, e outro ``editai`` no PATH, mais velho, não pode
    ganhar dele), ou o do PATH."""
    proprio = Path(sys.argv[0])
    if proprio.name.lower().startswith(("editai", "editar")):
        for candidato in (proprio, proprio.with_suffix(".exe")):
            if candidato.is_file():
                # sem desfazer o link: no macOS, o ~/.local/bin/editai aponta para o ambiente
                # do uv, que muda de lugar se o uv mudar
                return candidato.absolute()
    achado = shutil.which("editai")
    if achado:
        return Path(achado)
    raise ErroDoAtalho("Não achei o comando editai. Instale o Editai antes de criar o atalho.")


def _pastas_do_windows() -> dict[str, Path]:
    """O menu Iniciar e a Área de Trabalho do usuário (a da OneDrive, quando é ela)."""
    r = subprocess.run(["powershell", "-NoProfile", "-Command",
                        "[Environment]::GetFolderPath('Programs');"
                        "[Environment]::GetFolderPath('Desktop')"],
                       capture_output=True, text=True, timeout=60, check=False)
    linhas = [x.strip() for x in r.stdout.splitlines() if x.strip()]
    if r.returncode != 0 or len(linhas) != 2:
        raise ErroDoAtalho("O PowerShell não disse onde ficam o menu Iniciar e a Área de Trabalho.")
    return {"menu": Path(linhas[0]), "area": Path(linhas[1])}


def caminhos(sistema: str = sys.platform) -> list[Path]:
    """Onde ficam os atalhos deste sistema (existindo ou não)."""
    if sistema == "darwin":
        return [Path.home() / "Applications" / f"{NOME}.app"]
    if sistema == "win32":
        try:
            p = _pastas_do_windows()
        except (OSError, subprocess.SubprocessError, ErroDoAtalho):
            return []
        return [p["menu"] / f"{NOME}.lnk", p["area"] / f"{NOME}.lnk"]
    return [Path.home() / ".local" / "share" / "applications" / "editai.desktop"]


def _mac(alvo: Path) -> list[Path]:
    app = caminhos("darwin")[0]
    shutil.rmtree(app, ignore_errors=True)
    (app / "Contents" / "MacOS").mkdir(parents=True)
    (app / "Contents" / "Resources").mkdir()
    shutil.copyfile(_icone("icns"), app / "Contents" / "Resources" / "editai.icns")
    (app / "Contents" / "Info.plist").write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>{NOME}</string>
  <key>CFBundleDisplayName</key><string>{NOME}</string>
  <key>CFBundleIdentifier</key><string>{IDENTIFICADOR}</string>
  <key>CFBundleExecutable</key><string>abrir</string>
  <key>CFBundleIconFile</key><string>editai</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>{__version__}</string>
</dict>
</plist>
""", encoding="utf-8")
    abrir = app / "Contents" / "MacOS" / "abrir"
    # o Terminal roda o editai numa janela: é ela que mostra o endereço e que fecha o editor
    abrir.write_text(f'#!/bin/sh\nexec open -a Terminal "{alvo}"\n', encoding="utf-8")
    abrir.chmod(0o755)
    return [app]


def _windows(alvo: Path) -> list[Path]:
    from editor.ia import pasta_de_dados

    icone = pasta_de_dados() / "atalho" / "editai.ico"
    icone.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(_icone("ico"), icone)
    feitos = []
    for lnk in caminhos("win32"):
        lnk.parent.mkdir(parents=True, exist_ok=True)
        comando = ("$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:EDITAI_LNK);"
                   "$s.TargetPath = $env:EDITAI_ALVO; $s.IconLocation = $env:EDITAI_ICONE;"
                   "$s.WorkingDirectory = $env:USERPROFILE; $s.Description = 'Editai'; $s.Save()")
        # os caminhos vão pelo ambiente, e não dentro do comando: um apóstrofo no nome da pasta
        # do usuário quebraria a aspa do PowerShell
        r = subprocess.run(["powershell", "-NoProfile", "-Command", comando], capture_output=True,
                           text=True, timeout=60, check=False,
                           env={**os.environ, "EDITAI_LNK": str(lnk), "EDITAI_ALVO": str(alvo),
                                "EDITAI_ICONE": str(icone)})
        if r.returncode != 0:
            motivo = r.stderr.strip()[:200]
            raise ErroDoAtalho(f"O PowerShell não criou o atalho em {lnk}: {motivo}")
        feitos.append(lnk)
    return feitos


def _linux(alvo: Path) -> list[Path]:
    desktop = caminhos("linux")[0]
    desktop.parent.mkdir(parents=True, exist_ok=True)
    desktop.write_text(f"""[Desktop Entry]
Type=Application
Name={NOME}
Comment=Edita vídeos falados no estilo dos Shorts, no seu computador
Exec="{alvo}"
Icon={_icone("png")}
Terminal=true
Categories=AudioVideo;Video;
""", encoding="utf-8")
    return [desktop]


def criar(sistema: str = sys.platform) -> list[Path]:
    """Cria (ou refaz) o atalho deste sistema e devolve onde ele ficou."""
    alvo = executavel()
    if sistema == "darwin":
        return _mac(alvo)
    if sistema == "win32":
        return _windows(alvo)
    return _linux(alvo)


__all__ = ["IDENTIFICADOR", "NOME", "ErroDoAtalho", "caminhos", "criar", "executavel"]
