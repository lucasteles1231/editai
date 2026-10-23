"""Prepara uma versão nova: o número no ``pyproject.toml`` e no ``editor/__init__.py``, e a data
na seção dela do ``CHANGELOG.md`` (que precisa existir, escrita antes).

    uv run python instalador/nova_versao.py 0.2.0

Não faz commit nem tag: no fim, mostra os comandos. A tag ``v0.2.0`` no GitHub dispara o
workflow ``versao.yml``, que roda os testes, monta o pacote e os instaladores e publica.
"""
from __future__ import annotations

import datetime
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def trocar(caminho: Path, padrao: str, novo: str) -> None:
    texto = caminho.read_text(encoding="utf-8")
    trocado, n = re.subn(padrao, novo, texto, count=1, flags=re.M)
    if n != 1:
        raise SystemExit(f"não achei {padrao!r} em {caminho.name}")
    caminho.write_text(trocado, encoding="utf-8")


def main(argv: list[str]) -> int:
    if len(argv) != 1 or not re.fullmatch(r"\d+\.\d+\.\d+", argv[0]):
        raise SystemExit("uso: nova_versao.py X.Y.Z")
    versao = argv[0]
    changelog = RAIZ / "CHANGELOG.md"
    if not re.search(rf"^## \[{re.escape(versao)}\]", changelog.read_text(encoding="utf-8"), re.M):
        raise SystemExit(f"escreva antes a seção ## [{versao}] no CHANGELOG.md, com o que mudou")
    hoje = datetime.date.today().strftime("%d/%m/%Y")
    trocar(changelog, rf"^## \[{re.escape(versao)}\].*$", f"## [{versao}] — {hoje}")
    trocar(RAIZ / "pyproject.toml", r'^version = "[^"]+"$', f'version = "{versao}"')
    trocar(RAIZ / "editor" / "__init__.py", r'^__version__ = "[^"]+"$', f'__version__ = "{versao}"')
    print(f"pronto: {versao}, de {hoje}. Agora:\n"
          f"  uv lock\n"
          f'  git commit -am "Versão {versao}"\n'
          f"  git tag v{versao}\n"
          f"  git push --follow-tags")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
