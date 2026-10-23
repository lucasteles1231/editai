"""
O README é o resumo e o site (``docs/``) é o detalhe (a escolha do dono, 23/10/2026): os dois
mudam juntos. Aqui fica conferido que eles não se desencontram:

- todo link do README para o site cai numa página e numa âncora que existem;
- todo link e toda imagem entre as páginas do site existem (o ``vitepress build`` só confere a
  página, não a âncora);
- toda opção do ``editai`` está na página do terminal;
- os comandos de instalação são os mesmos no README, no site e no ``editor/versao.py``.

As âncoras são as do VitePress: sem acento, minúsculas, com hífen no lugar de espaço e
pontuação (``slugify`` de ``@mdit-vue/shared``).
"""
from __future__ import annotations

import argparse
import re
import unicodedata
from pathlib import Path

import pytest

from editor import cli, versao

RAIZ = Path(__file__).resolve().parents[1]
DOCS = RAIZ / "docs"
SITE = "https://lucasteles1231.github.io/editai/"


def ancora(titulo: str) -> str:
    """O slug do VitePress para um título."""
    t = re.sub(r"`([^`]*)`", r"\1", titulo)
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"[*_]", "", t).strip()
    t = unicodedata.normalize("NFKD", t)
    t = re.sub(r"[̀-ͯ]", "", t)
    t = re.sub(r"[\u0000-\u001f]", "", t)
    t = re.sub(r"[\s~`!@#$%^&*()\-_+=\[\]{}|\\;:\"'“”‘’<>,.?/]+", "-", t)
    t = re.sub(r"-{2,}", "-", t).strip("-")
    return re.sub(r"^(\d)", r"_\1", t).lower()


def _sem_codigo(texto: str) -> str:
    return re.sub(r"^```.*?^```", "", texto, flags=re.M | re.S)


def paginas() -> dict[str, Path]:
    """Cada página pelo endereço dela no site: ``"guia/minha-voz"``, ``""`` (o início)."""
    saida = {}
    for md in DOCS.rglob("*.md"):
        if "node_modules" in md.parts:
            continue
        rel = md.relative_to(DOCS).with_suffix("").as_posix()
        saida["" if rel == "index" else rel] = md
    return saida


def ancoras(md: Path) -> set[str]:
    texto = md.read_text(encoding="utf-8")
    incluido = re.search(r"<!--@include: (.+?)-->", texto)
    if incluido:
        texto += (md.parent / incluido[1]).read_text(encoding="utf-8")
    return {ancora(m[1]) for m in re.finditer(r"^#{1,6} (.+)$", _sem_codigo(texto), re.M)}


def _confere(destino: str, de_onde: str, problemas: list[str]) -> None:
    caminho, _, alvo = destino.partition("#")
    caminho = caminho.strip("/")
    todas = paginas()
    if caminho not in todas:
        problemas.append(f"{de_onde}: a página {caminho or '(início)'} não existe")
    elif alvo and alvo not in ancoras(todas[caminho]):
        problemas.append(f"{de_onde}: {caminho} não tem a âncora #{alvo}")


def _links(texto: str) -> list[str]:
    texto = _sem_codigo(texto)
    return [m[1] for m in re.finditer(r'\]\(([^)\s]+)\)|href="([^"]+)"', texto)
            for m in [m] if m[1]] + [m[1] for m in re.finditer(r'href="([^"]+)"', texto)]


def test_os_links_do_readme_para_o_site():
    problemas: list[str] = []
    readme = (RAIZ / "README.md").read_text(encoding="utf-8")
    for destino in _links(readme):
        if destino.startswith(SITE):
            _confere(destino[len(SITE):], "README", problemas)
    assert not problemas, "\n".join(problemas)
    # o README aponta para o site em cada função que resume
    assert len({d for d in _links(readme) if d.startswith(SITE)}) >= 20


def test_os_links_e_as_imagens_entre_as_paginas():
    problemas: list[str] = []
    for endereco, md in paginas().items():
        texto = md.read_text(encoding="utf-8")
        for destino in _links(texto):
            if re.match(r"^(https?:|mailto:)", destino):
                continue
            if destino.startswith("#"):
                if destino[1:] and destino[1:] not in ancoras(md):
                    problemas.append(f"{endereco}: sem a âncora {destino}")
                continue
            caminho = (md.parent / destino.split("#")[0]).resolve()
            if re.search(r"\.(png|svg|jpg|gif|webp)$", caminho.name):
                if not caminho.is_file():
                    problemas.append(f"{endereco}: a imagem {destino} não existe")
                continue
            relativo = caminho.relative_to(DOCS.resolve()).as_posix()
            _confere(relativo + ("#" + destino.split("#")[1] if "#" in destino else ""),
                     endereco, problemas)
        for m in re.finditer(r'srcset="([^"]+)"', texto):
            if not (md.parent / m[1]).resolve().is_file():
                problemas.append(f"{endereco}: a imagem {m[1]} não existe")
    assert not problemas, "\n".join(problemas)


def test_toda_opcao_do_terminal_esta_documentada():
    texto = (DOCS / "guia" / "no-terminal.md").read_text(encoding="utf-8")
    # (as escondidas da ajuda, o avesso de outra opção, como --sem-animacoes, ficam de fora)
    faltam = [op for acao in cli.argumentos()._actions if acao.help != argparse.SUPPRESS
              for op in acao.option_strings
              if op.startswith("--") and op not in ("--help", "--ajuda") and f"`{op}" not in texto]
    assert not faltam, f"opções sem documentação em docs/guia/no-terminal.md: {faltam}"


@pytest.mark.parametrize("sistema", ["darwin", "win32"])
def test_os_comandos_de_instalacao_sao_os_mesmos(sistema):
    comando = versao.comando_do_instalador(sistema)
    assert comando in (RAIZ / "README.md").read_text(encoding="utf-8")
    baixar = (DOCS / ".vitepress" / "theme" / "Baixar.vue").read_text(encoding="utf-8")
    assert comando.replace(versao.SITE, "${site}") in baixar
    assert f"const site = '{versao.SITE}';" in baixar


def test_as_versoes_do_site_sao_o_changelog():
    assert "<!--@include: ../CHANGELOG.md-->" in (DOCS / "versoes.md").read_text(encoding="utf-8")
    from editor import __version__

    assert f"## [{__version__}]" in (RAIZ / "CHANGELOG.md").read_text(encoding="utf-8")


def test_a_ancora_e_a_do_vitepress():
    assert ancora("O que cada função precisa") == "o-que-cada-funcao-precisa"
    assert ancora("Gerar a matriz") == "gerar-a-matriz"
    assert ancora("`--avatar NOME`") == "avatar-nome"
