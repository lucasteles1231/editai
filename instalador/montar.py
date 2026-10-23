"""Monta os anexos de uma versão (o workflow ``versao.yml``) e os instaladores do site
(``site.yml``).

    python instalador/montar.py --conferir v0.2.0      # a tag bate com o pyproject e o CHANGELOG?
    python instalador/montar.py dist                   # os instaladores, as notas e os SHA-256
    python instalador/montar.py SAIDA --so-scripts --versao 0.2.0   # só instalar.sh e .ps1

Os anexos de cada versão:

- ``instalar.sh`` e ``instalar.ps1``, com a versão gravada (o comando de uma linha do site usa
  os da última versão);
- ``Instalar-Editai-macOS.zip``, com o ``Instalar Editai.command`` dentro: o zip guarda a
  permissão de executar, que o navegador tira de um ``.command`` baixado solto;
- ``Instalar-Editai-Windows.cmd``, que roda o ``instalar.ps1`` desta versão no PowerShell
  (o ``.ps1`` baixado não abre com dois cliques);
- ``SHA256SUMS.txt``, com o hash de tudo o que está na pasta (o pacote ``.whl`` também).

As notas da versão saem da seção dela no ``CHANGELOG.md`` e vão para ``notas.md``, fora da
pasta dos anexos.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import stat
import sys
import tomllib
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
AQUI = Path(__file__).resolve().parent
REPOSITORIO = "lucasteles1231/editai"


def versao_do_projeto() -> str:
    projeto = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))
    return projeto["project"]["version"]


def notas(versao: str, changelog: Path = RAIZ / "CHANGELOG.md") -> str:
    """A seção ``## [X.Y.Z]`` do CHANGELOG, sem o título."""
    texto = changelog.read_text(encoding="utf-8")
    m = re.search(rf"^## \[{re.escape(versao)}\][^\n]*\n(.*?)(?=^## |\Z)", texto, re.M | re.S)
    if not m or not m[1].strip():
        raise SystemExit(f"o CHANGELOG.md não tem a seção ## [{versao}]")
    return m[1].strip() + "\n"


def conferir(tag: str) -> None:
    versao = versao_do_projeto()
    if tag.lstrip("v") != versao:
        raise SystemExit(f"a tag {tag} não é a versão do pyproject.toml ({versao})")
    from editor import __version__

    if __version__ != versao:
        raise SystemExit(f"editor/__init__.py diz {__version__}, e o pyproject.toml {versao}")
    notas(versao)
    print(f"ok: {tag}")


def _com_versao(nome: str, versao: str) -> str:
    texto = (AQUI / nome).read_text(encoding="utf-8")
    if "__VERSAO__" not in texto:
        raise SystemExit(f"{nome} não tem o __VERSAO__")
    return texto.replace("__VERSAO__", versao)


def scripts(saida: Path, versao: str) -> list[Path]:
    saida.mkdir(parents=True, exist_ok=True)
    feitos = []
    for nome in ("instalar.sh", "instalar.ps1"):
        destino = saida / nome
        # o .ps1 sai com CRLF e o .sh com LF: cada um no jeito do seu sistema
        texto = _com_versao(nome, versao)
        if nome.endswith(".ps1"):
            texto = texto.replace("\r\n", "\n").replace("\n", "\r\n")
        destino.write_bytes(texto.encode("utf-8"))
        feitos.append(destino)
    return feitos


def anexos(saida: Path, versao: str) -> list[Path]:
    feitos = scripts(saida, versao)
    # o macOS: o .command dentro de um zip, executável
    comando = _com_versao("instalar.sh", versao) + (
        '\nprintf "\\nAperte Enter para fechar esta janela."\nread -r _\n')
    zip_mac = saida / "Instalar-Editai-macOS.zip"
    with zipfile.ZipFile(zip_mac, "w", zipfile.ZIP_DEFLATED) as z:
        info = zipfile.ZipInfo("Instalar Editai.command", date_time=(2026, 1, 1, 0, 0, 0))
        info.external_attr = (stat.S_IFREG | 0o755) << 16
        info.compress_type = zipfile.ZIP_DEFLATED
        z.writestr(info, comando)
    feitos.append(zip_mac)
    # o Windows: um .cmd que roda o instalar.ps1 desta versão
    cmd = saida / "Instalar-Editai-Windows.cmd"
    endereco = f"https://github.com/{REPOSITORIO}/releases/download/v{versao}/instalar.ps1"
    cmd.write_bytes((
        "@echo off\r\n"
        f"echo Instalando o Editai {versao}...\r\n"
        f'powershell -NoProfile -ExecutionPolicy Bypass -Command "irm {endereco} | iex"\r\n'
        "echo.\r\n"
        "pause\r\n").encode("ascii"))
    feitos.append(cmd)
    return feitos


def somas(saida: Path) -> Path:
    linhas = []
    for f in sorted(saida.iterdir()):
        if f.is_file() and f.name != "SHA256SUMS.txt":
            linhas.append(f"{hashlib.sha256(f.read_bytes()).hexdigest()}  {f.name}")
    destino = saida / "SHA256SUMS.txt"
    destino.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return destino


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("saida", nargs="?", type=Path)
    p.add_argument("--conferir", metavar="TAG")
    p.add_argument("--so-scripts", action="store_true")
    p.add_argument("--versao", default="")
    a = p.parse_args(argv)
    if a.conferir:
        conferir(a.conferir)
        return 0
    if not a.saida:
        p.error("diga a pasta de saída")
    versao = a.versao or versao_do_projeto()
    if a.so_scripts:
        for f in scripts(a.saida, versao):
            print(f)
        return 0
    for f in anexos(a.saida, versao):
        print(f)
    print(somas(a.saida))
    notas_md = a.saida.parent / "notas.md"
    notas_md.write_text(notas(versao), encoding="utf-8")
    print(notas_md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
