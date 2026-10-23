"""
Tirar o Editai do computador: ``editai --desinstalar`` (tudo) e ``--desinstalar-voz`` (só o
motor da voz sintetizada, o grosso do espaço).

O que o Editai guarda fica nas pastas do sistema com o nome de antes, ``editor-de-video``
(as do ``platformdirs``: no macOS, ``Application Support`` e ``Caches``; no Windows, uma só,
com o cache dentro), mais o programa, criado pelo ``uv tool``:

- **os dados:** o motor da voz, as vozes gravadas, os avatares, os presets, os efeitos, os
  sons baixados e o ``config.json`` com as chaves do Gemini e do Pexels;
- **os temporários:** os envios, as transcrições, as narrações e as imagens;
- **o atalho "Editai"** que o instalador criou (:mod:`editor.atalho`);
- **o programa:** sai por último, pelo ``uv tool uninstall editai`` (no Windows, o comando é
  mostrado: o ``editai.exe`` aberto não deixa apagar).

Duas coisas são perguntadas à parte, com "não" de resposta padrão (a escolha do dono,
23/10/2026):

- **os modelos de transcrição e de recorte** (o Whisper e o MODNet), na pasta do Hugging Face,
  que outros programas também usam. Saem só as pastas exatas deles;
- **os vídeos editados**, na pasta padrão (``Filmes/editor-de-video``): são o trabalho da
  pessoa, e podem não ter cópia.

Com ``--sim`` nada é perguntado, e os dois só saem com ``--com-modelos`` e ``--com-videos``.
O ``uv`` e o Python que ele baixou ficam: são ferramentas gerais, e não do Editai.
"""
from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

#: O nome das pastas (o de antes do Editai, para ninguém perder a chave e as vozes).
NOME = "editor-de-video"
#: O nome da ferramenta no ``uv tool``.
FERRAMENTA = "editai"
#: Onde cada chave se cancela: apagar o arquivo não cancela a chave no serviço.
ONDE_CANCELAR = {"gemini_api_key": ("Gemini", "https://aistudio.google.com/apikey"),
                 "pexels_api_key": ("Pexels", "https://www.pexels.com/api/")}

Perguntar = Callable[[str], str]
Escrever = Callable[[str], None]


@dataclass(frozen=True)
class Item:
    """Uma coisa que sai: o que é, onde está e quanto ocupa."""

    rotulo: str
    caminho: Path
    bytes: int


# ── onde estão as coisas ─────────────────────────────────────────────────


def pastas_do_sistema() -> dict[str, Path]:
    """As pastas do Editai pelo papel de cada uma. No macOS e no Windows, os dados e a
    configuração são a mesma pasta; no Windows, o cache fica dentro dela."""
    from platformdirs import user_cache_dir, user_config_dir, user_data_dir

    return {"dados": Path(user_data_dir(NOME, appauthor=False)),
            "configuracao": Path(user_config_dir(NOME, appauthor=False)),
            "temporarios": Path(user_cache_dir(NOME, appauthor=False))}


def pasta_dos_videos() -> Path:
    """A pasta padrão dos vídeos editados (a mesma de ``servidor.pasta_de_saida_padrao``)."""
    from platformdirs import user_videos_dir

    return Path(user_videos_dir()) / NOME


def cache_do_hugging_face() -> Path:
    from huggingface_hub import constants

    return Path(constants.HF_HUB_CACHE)


def repositorios_dos_modelos() -> list[str]:
    """Os modelos que o Editai baixa para o cache do Hugging Face: os quatro tamanhos do
    Whisper e o MODNet. O da voz sintetizada vai para a pasta do motor."""
    from editor import recorte, transcricao

    return [f"Systran/faster-whisper-{m}" for m in transcricao.MODELOS] + [recorte.REPOSITORIO]


def achar_uv() -> str | None:
    from editor import motor_de_voz

    return motor_de_voz.achar_uv()


# ── o tamanho ────────────────────────────────────────────────────────────


def tamanho(caminho: Path) -> int:
    """Os bytes de um arquivo ou de uma pasta inteira (sem seguir atalhos)."""
    if caminho.is_symlink() or caminho.is_file():
        try:
            return caminho.lstat().st_size
        except OSError:
            return 0
    total = 0
    for raiz, _pastas, arquivos in os.walk(caminho):
        for nome in arquivos:
            with contextlib.suppress(OSError):
                total += os.lstat(os.path.join(raiz, nome)).st_size
    return total


def legivel(n: int) -> str:
    """Como o Finder e o Explorer mostram: "8,4 GB", "114 MB", "552 KB"."""
    for unidade, base in (("GB", 1e9), ("MB", 1e6), ("KB", 1e3)):
        if n >= base:
            valor = n / base
            numero = f"{valor:.1f}".replace(".", ",") if valor < 10 else f"{valor:.0f}"
            return f"{numero} {unidade}"
    return f"{n} bytes"


def _curto(caminho: Path) -> str:
    """O caminho com ``~`` no lugar da pasta pessoal, para caber na linha."""
    casa = str(Path.home())
    texto = str(caminho)
    return "~" + texto[len(casa):] if texto.startswith(casa + os.sep) else texto


# ── o inventário ─────────────────────────────────────────────────────────


def _dentro(filha: Path, mae: Path) -> bool:
    try:
        filha.resolve().relative_to(mae.resolve())
        return True
    except ValueError:
        return False


def principais() -> list[Item]:
    """O que sempre sai: o motor da voz (à parte, por ser o grosso) e as pastas do sistema,
    sem repetir a que está dentro de outra (o cache do Windows, dentro dos dados)."""
    papeis: dict[Path, list[str]] = {}
    for papel, pasta in pastas_do_sistema().items():
        papeis.setdefault(pasta, []).append(papel)
    raizes = [p for p in papeis if not any(o != p and _dentro(p, o) for o in papeis)]
    rotulos = {"dados": ["as vozes gravadas", "os avatares", "os presets", "os sons baixados"],
               "configuracao": ["as chaves do Gemini e do Pexels"],
               "temporarios": ["os temporários (envios, transcrições, narrações e imagens)"]}
    itens: list[Item] = []
    for raiz in raizes:
        if not raiz.exists():
            continue
        motor = raiz / "motor-de-voz"
        if motor.is_dir():
            itens.append(Item("o motor da voz sintetizada", motor, tamanho(motor)))
        nomes = [n for p, ps in papeis.items() if p == raiz or _dentro(p, raiz) for papel in ps
                 for n in rotulos[papel]]
        rotulo = ", ".join(nomes[:-1]) + " e " + nomes[-1] if len(nomes) > 1 else nomes[0]
        # (o resto da pasta, sem passar de novo pelos milhares de arquivos do motor)
        resto = sum(tamanho(c) for c in raiz.iterdir() if c != motor)
        itens.append(Item(rotulo, raiz, resto))
    return itens


def caminhos_dos_atalhos() -> list[Path]:
    from editor import atalho

    return atalho.caminhos()


def atalhos() -> list[Item]:
    """O atalho "Editai" que o instalador criou (``editai --criar-atalho``)."""
    return [Item("o atalho Editai", c, tamanho(c)) for c in caminhos_dos_atalhos() if c.exists()]


def modelos() -> list[Item]:
    """As pastas dos modelos do Editai no cache do Hugging Face (as de outros ficam)."""
    raiz = cache_do_hugging_face()
    itens = []
    for repo in repositorios_dos_modelos():
        pasta = raiz / ("models--" + repo.replace("/", "--"))
        if pasta.is_dir():
            itens.append(Item(f"o modelo {repo}", pasta, tamanho(pasta)))
    return itens


def videos() -> Item | None:
    pasta = pasta_dos_videos()
    return Item("os vídeos editados", pasta, tamanho(pasta)) if pasta.is_dir() else None


def programa() -> tuple[Item, str] | None:
    """O programa instalado pelo ``uv tool`` e o ``uv`` que o tira; ``None`` quando o Editai
    não veio por ele (rodando do código, por exemplo)."""
    uv = achar_uv()
    if not uv:
        return None
    try:
        r = subprocess.run([uv, "tool", "dir"], capture_output=True, text=True, timeout=30,
                           check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    pasta = Path(r.stdout.strip()) / FERRAMENTA
    if r.returncode != 0 or not pasta.is_dir():
        return None
    return Item("o programa (os comandos editai e editar)", pasta, tamanho(pasta)), uv


def chaves_guardadas() -> list[str]:
    """Os serviços com chave no ``config.json`` (para lembrar de cancelar, depois)."""
    arquivo = pastas_do_sistema()["configuracao"] / "config.json"
    try:
        guardadas = json.loads(arquivo.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(guardadas, dict):
        return []
    return [nome for nome in ONDE_CANCELAR if str(guardadas.get(nome) or "").strip()]


# ── apagar ───────────────────────────────────────────────────────────────


def _apagar(caminho: Path) -> str:
    """Apaga e diz o que deu errado ("" quando deu certo)."""
    try:
        if caminho.is_dir() and not caminho.is_symlink():
            shutil.rmtree(caminho)
        else:
            caminho.unlink(missing_ok=True)
    except OSError as erro:
        return erro.strerror or str(erro)
    return ""


def _sim(resposta: str) -> bool:
    return resposta.strip().lower() in ("s", "sim")


def _perguntar_extra(rotulo: str, itens: list[Item], *, ja: bool, sim: bool, opcao: str,
                     perguntar: Perguntar, escrever: Escrever) -> bool:
    if not itens:
        return False
    total = sum(i.bytes for i in itens)
    if ja:
        return True
    if sim:
        escrever(f"  ficam {rotulo} ({legivel(total)}); para apagar também, use {opcao}")
        return False
    return _sim(perguntar(f"Apagar também {rotulo} ({legivel(total)})? [s/N] "))


def tudo(*, sim: bool = False, com_videos: bool = False, com_modelos: bool = False,
         perguntar: Perguntar = input, escrever: Escrever = print) -> int:
    """``editai --desinstalar``: mostra tudo o que o Editai guardou, pergunta o que é da
    pessoa ou de outros programas, confirma com "sim" e apaga. O programa sai por último."""
    itens = [*principais(), *atalhos()]
    dos_modelos = modelos()
    dos_videos = videos()
    do_programa = programa()
    if not (itens or dos_modelos or dos_videos or do_programa):
        escrever("O Editai não guardou nada neste computador.")
        return 0

    escrever("O que o Editai guardou neste computador:\n")
    sempre = [*itens, *([do_programa[0]] if do_programa else [])]
    for i in sempre:
        escrever(f"  {legivel(i.bytes):>8}  {i.rotulo}\n            {_curto(i.caminho)}")
    if dos_modelos:
        escrever(f"  {legivel(sum(i.bytes for i in dos_modelos)):>8}  os modelos de transcrição "
                 f"e de recorte (pergunto à parte)\n            {_curto(cache_do_hugging_face())}")
    if dos_videos:
        escrever(f"  {legivel(dos_videos.bytes):>8}  os vídeos editados (pergunto à parte)\n"
                 f"            {_curto(dos_videos.caminho)}")
    escrever("")

    if _perguntar_extra("os modelos de transcrição e de recorte, na pasta do Hugging Face, que "
                        "outros programas também podem usar", dos_modelos, ja=com_modelos, sim=sim,
                        opcao="--com-modelos", perguntar=perguntar, escrever=escrever):
        sempre[len(itens):len(itens)] = dos_modelos
    if _perguntar_extra("os vídeos editados", [dos_videos] if dos_videos else [], ja=com_videos,
                        sim=sim, opcao="--com-videos", perguntar=perguntar, escrever=escrever):
        sempre.insert(len(sempre) - (1 if do_programa else 0), dos_videos)

    total = sum(i.bytes for i in sempre)
    pergunta = f'Apagar {legivel(total)}? Digite "sim" para confirmar: '
    if not sim and perguntar(pergunta).strip().lower() != "sim":
        escrever("Nada foi apagado.")
        return 1

    cancelar = chaves_guardadas()
    falhas = 0
    for i in sempre:
        if do_programa and i is do_programa[0]:
            continue
        erro = _apagar(i.caminho)
        if erro:
            falhas += 1
            escrever(f"  não consegui apagar {_curto(i.caminho)}: {erro}")
        else:
            escrever(f"  apagado: {i.rotulo}")
    for nome in cancelar:
        servico, endereco = ONDE_CANCELAR[nome]
        escrever(f"A chave do {servico} saiu deste computador, mas continua valendo no {servico}. "
                 f"Para cancelar, apague-a em {endereco}")

    if do_programa:
        comando = f"uv tool uninstall {FERRAMENTA}"
        if sys.platform == "win32":
            escrever(f"Para terminar, feche o Editai e rode: {comando}")
        else:
            r = subprocess.run([do_programa[1], "tool", "uninstall", FERRAMENTA],
                               capture_output=True, text=True, timeout=120, check=False)
            if r.returncode == 0:
                escrever(f"  apagado: {do_programa[0].rotulo}")
            else:
                falhas += 1
                escrever(f"  o uv não conseguiu tirar o programa; rode: {comando}")
    escrever("Pronto: o Editai saiu deste computador." if not falhas
             else "Quase: o que não saiu está listado acima.")
    return 1 if falhas else 0


def so_o_motor(*, sim: bool = False, perguntar: Perguntar = input,
               escrever: Escrever = print) -> int:
    """``editai --desinstalar-voz``: o motor e o modelo saem; as vozes gravadas ficam, para
    quando a pessoa instalar de novo."""
    from editor import motor_de_voz

    pasta = motor_de_voz.pasta()
    if not pasta.exists():
        escrever("A voz sintetizada não está instalada.")
        return 0
    n = tamanho(pasta)
    pergunta = (f"Apagar o motor da voz sintetizada ({legivel(n)}, {_curto(pasta)})? "
                "As vozes gravadas ficam. [s/N] ")
    if not sim and not _sim(perguntar(pergunta)):
        escrever("Nada foi apagado.")
        return 1
    try:
        motor_de_voz.desinstalar()
    except motor_de_voz.ErroDoMotor as erro:
        escrever(f"erro: {erro}")
        return 1
    escrever(f"Pronto: {legivel(n)} liberados.")
    return 0


__all__ = ["FERRAMENTA", "NOME", "ONDE_CANCELAR", "Item", "atalhos", "cache_do_hugging_face",
           "caminhos_dos_atalhos", "chaves_guardadas", "legivel", "modelos", "pasta_dos_videos",
           "pastas_do_sistema", "principais", "programa", "repositorios_dos_modelos", "so_o_motor",
           "tamanho", "tudo", "videos"]
