"""
O que o Editai baixa, num lugar só, e a regra que vale para quem usa: **nada baixa sem o ok
dela**.

Cada componente diz o que é, para que serve, o tamanho, a licença e se já está instalado. O
tamanho é o dos arquivos no commit fixado de cada modelo, medido na fonte quando o commit foi
escolhido (``tests/test_componentes.py`` confere a conta contra os arquivos). Assim o plano
mostra o tamanho certo **sem ir à internet** antes do ok.

**A trava.** Todo download do Editai passa por :func:`exigir` (ou :func:`pode_baixar`, para o
que tem reserva). Sem o ok, ele não baixa:

- o que é **essencial** para a tarefa (o Whisper, numa edição) levanta :class:`PrecisaDeOk`, com a
  lista do que falta. A página mostra "Aprovar e baixar 486 MB" e manda o pedido de novo com o
  ok; o terminal pergunta ``[s/N]``, e ``--sim`` aprova sem perguntar;
- o que tem **reserva** (os sons do tema "Notícia", sem licença livre) não baixa, e toca a
  reserva. Ele aparece no plano, para quem quiser.

O ok vale para o processo inteiro e passa aos processos filhos (o auditor calcula os textos num
processo à parte) pela variável ``EDITAI_APROVADOS``: os ids separados por vírgula, ou ``*``
para tudo. Instalado é instalado: o ok só conta para o que ainda não está no computador.

**Os motores à parte** (a IA local, a voz local e o motor de "Minha voz") têm a instalação
própria, com o botão "Instalar" e ``--instalar-…``: o clique é o ok. Eles estão aqui para
aparecer na lista do que está instalado.
"""
from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

logger = logging.getLogger(__name__)

#: Os ids aprovados por quem usa (``*`` aprova tudo). Vai pelo ambiente, para os processos
#: filhos herdarem.
VARIAVEL = "EDITAI_APROVADOS"
TUDO = "*"

#: O andamento de um download: a fração (0 a 1) e um texto curto ("120 de 486 MB").
Andamento = Callable[[float, str], None]


@dataclass(frozen=True)
class Componente:
    id: str
    #: Como aparece para quem usa: "o Whisper small".
    nome: str
    para_que: str
    #: Os bytes que baixa (os arquivos no commit fixado).
    bytes: int
    licenca: str
    link: str
    #: Sem ele, a tarefa não sai. O que não é essencial tem reserva.
    essencial: bool = True
    #: Os motores à parte se instalam pelo botão deles, e não pelo plano.
    a_parte: bool = False
    #: O tamanho escrito, quando ele não é exato (os motores à parte).
    tamanho_escrito: str = ""

    def tamanho(self) -> str:
        return self.tamanho_escrito or legivel(self.bytes)

    def para_dict(self) -> dict:
        return {"id": self.id, "nome": self.nome, "para_que": self.para_que,
                "bytes": self.bytes, "tamanho": self.tamanho(), "licenca": self.licenca,
                "link": self.link, "essencial": self.essencial, "a_parte": self.a_parte,
                "instalado": instalado(self.id)}


class PrecisaDeOk(Exception):
    """O que falta baixar, e que quem usa ainda não aprovou."""

    def __init__(self, faltam: Sequence[Componente]):
        self.faltam = list(faltam)
        nomes = ", ".join(f"{c.nome} ({c.tamanho()})" for c in self.faltam)
        super().__init__(f"precisa do seu ok para baixar: {nomes}")

    def bytes(self) -> int:
        return sum(c.bytes for c in self.faltam)

    def para_dict(self) -> dict:
        return {"precisa_de_ok": [c.para_dict() for c in self.faltam],
                "bytes": self.bytes(), "tamanho": legivel(self.bytes()),
                "detail": str(self)}


def legivel(n: int) -> str:
    from editor import desinstalar

    return desinstalar.legivel(n)


# ── o catálogo ────────────────────────────────────────────────────────────
#: O Whisper de cada tamanho: os arquivos que o faster-whisper usa
#: (``transcricao.ARQUIVOS_DO_MODELO``), no commit fixado (``transcricao.REVISOES``), medidos
#: em 31/10/2026.
BYTES_DO_WHISPER = {"tiny": 78_203_619, "base": 147_882_941, "small": 486_212_372,
                    "medium": 1_530_571_735}
#: Os três arquivos do auditor (``auditor.ARQUIVOS``) e o do recorte (``recorte.ARQUIVO``).
BYTES_DO_AUDITOR = 412_354_647
BYTES_DO_RECORTE = 25_888_640


def _whisper(modelo: str) -> Componente:
    return Componente(
        f"whisper-{modelo}", f"o Whisper {modelo}",
        "transcreve a fala, no seu computador (o áudio não sai dele)",
        BYTES_DO_WHISPER[modelo], "MIT", f"https://huggingface.co/Systran/faster-whisper-{modelo}")


def _bytes_do_ruido() -> int:
    from editor import ruido

    return ruido.BYTES


def _sons_do_noticia() -> int:
    from editor import sons

    return sum(int(item["bytes"]) for item in sons.catalogo()["baixados"].values())


def catalogo() -> list[Componente]:
    """Tudo o que o Editai pode baixar, na ordem em que aparece para quem usa."""
    return [
        *(_whisper(m) for m in BYTES_DO_WHISPER),
        Componente("recorte", "o recorte da pessoa (MODNet)",
                   "tira o fundo da pessoa na montagem e na thumbnail", BYTES_DO_RECORTE,
                   "Apache-2.0", "https://huggingface.co/Xenova/modnet"),
        Componente("auditor", "o auditor das fotos (SigLIP 2)",
                   "confere se cada foto achada pelo tema mostra o que a fala diz",
                   BYTES_DO_AUDITOR, "Apache-2.0",
                   "https://huggingface.co/onnx-community/siglip2-base-patch16-224-ONNX"),
        Componente("ruido", "o redutor de ruído (DeepFilterNet3)",
                   "tira o ventilador, a rua, o teclado e o chiado da fala, no seu computador; "
                   "sem ele, a voz fica como veio", _bytes_do_ruido(),
                   "MIT/Apache-2.0 (o DeepFilterNet3) e MIT (o deepfilter-stream)",
                   "https://github.com/wuxuedaifu/deepfilter-stream", essencial=False),
        Componente("sons-noticia", "os sons do tema Notícia",
                   "quatro sons do Remotion nos cartões do tema Notícia; sem eles, tocam uns "
                   "parecidos que já vêm no Editai", _sons_do_noticia(),
                   "sem licença livre (o Remotion deixa usar, sem garantia)",
                   "https://remotion.media", essencial=False),
        Componente("ia-local", "a IA local (o Qwen3.5-4B e o llama-server)",
                   "o roteiro, as cenas, a matriz e o avatar, no seu computador",
                   3_500_000_000, "MIT (llama.cpp) e Apache-2.0 (Qwen3.5-4B)",
                   "https://huggingface.co/unsloth/Qwen3.5-4B-GGUF", a_parte=True,
                   tamanho_escrito="uns 3,5 GB"),
        Componente("voz-local", "a voz local (o Piper, com a voz Faber)",
                   "narra o roteiro no seu computador", 210_000_000,
                   "GPL-3.0 (o Piper, num ambiente à parte) e MIT (a voz Faber)",
                   "https://huggingface.co/rhasspy/piper-voices", a_parte=True,
                   tamanho_escrito="uns 210 MB"),
        Componente("motor-de-voz", "o motor de Minha voz (o Qwen3-TTS)",
                   "narra com a sua voz, a partir de uma gravação", 3_500_000_000, "Apache-2.0",
                   "https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-Base", a_parte=True,
                   tamanho_escrito="uns 3,5 GB"),
    ]


def pegar(id_: str) -> Componente:
    for c in catalogo():
        if c.id == id_:
            return c
    raise KeyError(f"componente desconhecido: {id_}")


def instalado(id_: str) -> bool:
    """Se já está no computador (sem ir à internet). Com o falso dos testes ligado, conta como
    instalado: o falso não baixa nada."""
    if id_.startswith("whisper-"):
        from editor import transcricao

        return transcricao.falso() or transcricao.modelo_baixado(id_.removeprefix("whisper-"))
    if id_ == "recorte":
        from editor import recorte

        return recorte.modelo_baixado()
    if id_ == "auditor":
        from editor import auditor

        return auditor.baixado()
    if id_ == "sons-noticia":
        from editor import sons

        return sons.baixados_guardados()
    if id_ == "ruido":
        from editor import ruido

        return ruido.instalado()
    if id_ == "ia-local":
        from editor import ia_local

        return ia_local.instalado()
    if id_ == "voz-local":
        from editor import voz_local

        return voz_local.instalado()
    if id_ == "motor-de-voz":
        from editor import motor_de_voz

        return motor_de_voz.instalado()
    raise KeyError(f"componente desconhecido: {id_}")


# ── o ok de quem usa ──────────────────────────────────────────────────────
_trava = threading.Lock()
#: O que quem usa disse que não quer agora (só os que têm reserva): não pergunta de novo.
_recusados: set[str] = set()


def aprovados() -> set[str]:
    return {i.strip() for i in os.environ.get(VARIAVEL, "").split(",") if i.strip()}


def aprovado(id_: str) -> bool:
    ok = aprovados()
    return TUDO in ok or id_ in ok


def aprovar(ids: Iterable[str]) -> None:
    """Quem usa aprovou baixar ``ids`` (``*`` para tudo)."""
    novos = {str(i).strip() for i in ids if str(i).strip()}
    if not novos:
        return
    with _trava:
        os.environ[VARIAVEL] = ",".join(sorted(aprovados() | novos))
        _recusados.difference_update(novos)
    if "sons-noticia" in novos or TUDO in novos:
        from editor import sons

        sons.esquecer_as_reservas()


def recusar(ids: Iterable[str]) -> None:
    """Quem usa não quis baixar agora (vale só para o que tem reserva)."""
    with _trava:
        _recusados.update(i for i in ids if not pegar(i).essencial)


def recusado(id_: str) -> bool:
    return id_ in _recusados


def esquecer() -> None:
    """Volta ao começo: nada aprovado, nada recusado (os testes usam)."""
    with _trava:
        os.environ.pop(VARIAVEL, None)
        _recusados.clear()


def exigir(*ids: str) -> None:
    """Para antes de baixar o que quem usa não aprovou. O que já está instalado passa."""
    faltam = [pegar(i) for i in ids if not aprovado(i) and not instalado(i)]
    if faltam:
        raise PrecisaDeOk(faltam)


def pode_baixar(id_: str) -> bool:
    """Para o que tem reserva: se pode baixar agora (sem o ok, a reserva toca)."""
    return aprovado(id_)


def faltando(ids: Iterable[str]) -> list[Componente]:
    """Do que ``ids`` precisa: o que não está instalado e não foi aprovado nem recusado."""
    vistos, saida = set(), []
    for i in ids:
        if i in vistos:
            continue
        vistos.add(i)
        if not instalado(i) and not aprovado(i) and not recusado(i):
            saida.append(pegar(i))
    return saida


def a_baixar(ids: Iterable[str]) -> list[Componente]:
    """Do que ``ids`` precisa: o que foi aprovado e ainda não está no computador."""
    return [pegar(i) for i in dict.fromkeys(ids)
            if aprovado(i) and not instalado(i) and not pegar(i).a_parte]


# ── tirar do computador ───────────────────────────────────────────────────
#: O repositório do Hugging Face de cada modelo do catálogo (a pasta exata dele no cache).
def _repositorio(id_: str) -> str | None:
    if id_.startswith("whisper-"):
        return f"Systran/faster-whisper-{id_.removeprefix('whisper-')}"
    if id_ == "recorte":
        from editor import recorte

        return recorte.REPOSITORIO
    if id_ == "auditor":
        from editor import auditor

        return auditor.REPOSITORIO
    return None


def desinstalar(id_: str) -> int:
    """Tira ``id_`` do computador (só a pasta exata dele) e devolve os bytes que saíram. Depois,
    usar de novo pede o ok de novo. Os motores à parte saem pelo botão deles."""
    import shutil

    from editor import desinstalar as desinstalar_mod

    c = pegar(id_)
    if c.a_parte:
        raise ValueError(f"{c.nome} sai pelo botão dele, no cartão de cada um")
    if id_ == "ruido":
        from editor import ruido

        saiu = ruido.desinstalar()
        _esquecer_o_ok(id_)
        return saiu
    if id_ == "sons-noticia":
        from editor import sons

        pastas = [sons.pasta_dos_baixados() / f"{nome}.wav" for nome in sons.catalogo()["baixados"]]
    else:
        repo = _repositorio(id_)
        pastas = [desinstalar_mod.cache_do_hugging_face() / ("models--" + repo.replace("/", "--"))]
    saiu = 0
    for caminho in pastas:
        if not caminho.exists():
            continue
        saiu += desinstalar_mod.tamanho(caminho)
        if caminho.is_dir():
            shutil.rmtree(caminho)
        else:
            caminho.unlink()
    _soltar(id_)
    _esquecer_o_ok(id_)
    logger.info("tirado: %s (%d bytes)", id_, saiu)
    return saiu


def _esquecer_o_ok(id_: str) -> None:
    """Depois de sair do computador, usar de novo pede o ok de novo."""
    with _trava:
        restantes = aprovados() - {id_}
        if restantes:
            os.environ[VARIAVEL] = ",".join(sorted(restantes))
        else:
            os.environ.pop(VARIAVEL, None)


def _soltar(id_: str) -> None:
    """Fecha o que estava aberto na memória do modelo que saiu."""
    if id_ == "auditor":
        from editor import auditor

        auditor.soltar()
    elif id_ == "recorte":
        from editor import recorte

        recorte.soltar()
    elif id_ == "sons-noticia":
        from editor import sons

        sons.esquecer_as_reservas()


# ── o que cada tarefa usa ─────────────────────────────────────────────────
def da_edicao(edicao, montagem=None, arquivos=()) -> list[str]:
    """Os componentes que uma edição usa: o Whisper do tamanho escolhido, o recorte da pessoa
    (na montagem com o MODNet), os sons do tema, se ele tiver os baixados, e o redutor de
    ruído, se a fala (``arquivos``) tiver ruído para tirar."""
    from editor import ruido, sons

    ids = [f"whisper-{edicao.modelo}"]
    if arquivos and ruido.forca_dos_arquivos(edicao.ruido, list(arquivos))[0] != "nada":
        ids.append("ruido")
    if montagem is not None and montagem.pessoa is not None and montagem.recorte == "modnet":
        ids.append("recorte")
    if edicao.sons and sons.baixados_do_tema(edicao.tema_dos_sons):
        ids.append("sons-noticia")
    return ids


def pedir_ok(ids: Iterable[str]) -> None:
    """Levanta :class:`PrecisaDeOk` com tudo o que ``ids`` ainda precisa do ok: os essenciais e
    os que têm reserva (estes, até quem usa recusar). Sem nada faltando, passa."""
    faltam = faltando(ids)
    if faltam:
        raise PrecisaDeOk(faltam)


# ── baixar, com o andamento ───────────────────────────────────────────────
def _barra(avisar: Callable[[int], None]):
    """Uma classe de barra do ``tqdm`` que conta os bytes para ``avisar``, sem desenhar nada.
    O ``huggingface_hub`` cria a barra com ela (``tqdm_class``)."""
    from tqdm.auto import tqdm

    class Barra(tqdm):
        def __init__(self, *args, **kwargs):
            kwargs["disable"] = True
            super().__init__(*args, **kwargs)

        def update(self, n=1):
            avisar(int(n or 0))
            return super().update(n)

    return Barra


def _do_hugging_face(repo: str, revisao: str, arquivos: Sequence[str], total: int,
                     andamento: Andamento, cancelar: Callable[[], bool]) -> None:
    from huggingface_hub import hf_hub_download

    feito = 0

    def avisar(n: int) -> None:
        nonlocal feito
        if cancelar():
            raise InterruptedError("download cancelado")
        feito += n
        andamento(min(1.0, feito / max(total, 1)), f"{legivel(feito)} de {legivel(total)}")

    andamento(0.0, f"0 de {legivel(total)}")
    for nome in arquivos:
        hf_hub_download(repo, nome, revision=revisao, tqdm_class=_barra(avisar))
    andamento(1.0, legivel(total))


def baixar(id_: str, andamento: Andamento | None = None,
           cancelar: Callable[[], bool] = lambda: False) -> None:
    """Baixa ``id_`` agora, com o andamento em bytes. Só depois do ok (:func:`aprovar`)."""
    exigir_ok = pegar(id_)
    if not aprovado(id_):
        raise PrecisaDeOk([exigir_ok])
    andamento = andamento or (lambda fracao, texto: None)
    if instalado(id_):
        andamento(1.0, "já instalado")
        return
    if id_.startswith("whisper-"):
        from editor import transcricao

        modelo = id_.removeprefix("whisper-")
        _do_hugging_face(f"Systran/faster-whisper-{modelo}", transcricao.REVISOES[modelo],
                         transcricao.ARQUIVOS_DO_MODELO, BYTES_DO_WHISPER[modelo], andamento,
                         cancelar)
    elif id_ == "auditor":
        from editor import auditor

        _do_hugging_face(auditor.REPOSITORIO, auditor.REVISAO, list(auditor.ARQUIVOS),
                         BYTES_DO_AUDITOR, andamento, cancelar)
        auditor.conferir_baixados()
    elif id_ == "recorte":
        from editor import recorte

        _do_hugging_face(recorte.REPOSITORIO, recorte.REVISAO, [recorte.ARQUIVO],
                         BYTES_DO_RECORTE, andamento, cancelar)
    elif id_ == "ruido":
        from editor import ruido

        ruido.baixar(andamento, cancelar)
    elif id_ == "sons-noticia":
        from editor import sons

        nomes = list(sons.catalogo()["baixados"])
        for k, nome in enumerate(nomes):
            andamento(k / len(nomes), f"{k} de {len(nomes)} sons")
            sons.baixar(nome)
        andamento(1.0, f"{len(nomes)} sons")
    else:
        raise ValueError(f"{exigir_ok.nome} se instala pelo botão dele, e não pelo plano")
    logger.info("baixado: %s", id_)


__all__ = [
    "TUDO",
    "VARIAVEL",
    "Componente",
    "PrecisaDeOk",
    "a_baixar",
    "aprovado",
    "aprovados",
    "aprovar",
    "baixar",
    "catalogo",
    "da_edicao",
    "esquecer",
    "exigir",
    "faltando",
    "instalado",
    "legivel",
    "pedir_ok",
    "pegar",
    "pode_baixar",
    "recusado",
    "recusar",
]
