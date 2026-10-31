"""
As edições pedidas pela interface: uma por vez, numa thread, com progresso.

Uma thread e não processos: o modo "spawn" de multiprocessamento do Windows
reimportaria o servidor inteiro em cada processo filho, e uma edição já ocupa todos os
núcleos (o Whisper e o x264 usam vários sozinhos).

**Cada parte tem a sua barra** (:class:`Parte`): cada download aprovado, a transcrição, os
cortes, a escolha das frases, o desenho e o fim do arquivo. O "quanto falta" de cada uma vem
da velocidade dela mesma, depois de 5% feitos. A barra geral continua, como a soma pesada das
partes.
"""
from __future__ import annotations

import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from editor import bloqueio, componentes, render
from editor import saida as saida_mod
from editor.montagem import Montagem
from editor.opcoes import OpcoesDeEdicao

#: Quanto cada etapa pesa na barra de progresso (início, fim).
PESOS = {"sincronizando": (0.0, 0.0), "transcrevendo": (0.0, 0.35), "limpando": (0.35, 0.35),
         "cortando": (0.35, 0.37),
         "escolhendo": (0.37, 0.39), "desenhando": (0.39, 0.97), "finalizando": (0.97, 1.0),
         "pronto": (1.0, 1.0)}
NOMES = {"sincronizando": "Sincronizando o som à parte", "transcrevendo": "Transcrevendo a fala",
         "limpando": "Tirando o ruído",
         "cortando": "Cortando os silêncios", "escolhendo": "Escolhendo o que entra",
         "desenhando": "Desenhando legenda, zoom e ícones", "finalizando": "Finalizando o arquivo",
         "pronto": "Pronto"}
#: As partes de toda edição, na ordem. As que só algumas têm (a sincronia) entram quando
#: começam, no lugar delas.
ETAPAS = ("transcrevendo", "cortando", "escolhendo", "desenhando", "finalizando")
#: Com downloads, eles ocupam este pedaço da barra geral (divididos pelos bytes), e a edição o
#: resto: um download de 486 MB leva, numa conexão comum, tanto quanto a edição de um vídeo
#: curto.
PESO_DOS_DOWNLOADS = 0.3
#: O "quanto falta" de uma parte só aparece depois disto feito: antes, a velocidade engana.
FEITO_PARA_ESTIMAR = 0.05


class Ocupado(Exception):
    """Já há uma edição rodando."""


@dataclass
class Parte:
    """Uma parte do processamento, com a sua barra."""

    id: str
    nome: str
    estado: str = "esperando"          # esperando | rodando | pronto | pulada | erro | cancelada
    fracao: float = 0.0
    detalhe: str = ""
    comeco: float | None = None
    fim: float | None = None
    #: Para os downloads: os bytes, que pesam a parte na barra geral.
    bytes: int = 0

    def andar(self, fracao: float, detalhe: str = "") -> None:
        if self.estado == "esperando":
            self.estado, self.comeco = "rodando", time.monotonic()
        elif self.estado in ("pronto", "pulada"):
            self.estado = "rodando"     # a etapa que volta (os cortes, ao tratar a voz)
        self.fracao = min(1.0, max(0.0, fracao))
        if detalhe:
            self.detalhe = detalhe

    def acabar(self, estado: str = "pronto") -> None:
        if self.estado in ("pronto", "pulada", "erro", "cancelada"):
            return
        if estado == "pronto" and self.estado == "esperando":
            estado = "pulada"           # a parte que a edição não usou (a escolha, no "Tudo")
        self.estado, self.fim = estado, time.monotonic()
        if estado == "pronto":
            self.fracao = 1.0

    def falta_s(self) -> float | None:
        if self.estado != "rodando" or self.fracao < FEITO_PARA_ESTIMAR or self.comeco is None:
            return None
        decorrido = time.monotonic() - self.comeco
        return max(0.0, decorrido / self.fracao * (1 - self.fracao))

    def para_dict(self) -> dict:
        return {"id": self.id, "nome": self.nome, "estado": self.estado,
                "fracao": round(self.fracao, 4), "detalhe": self.detalhe,
                "falta_s": self.falta_s()}


def _partes(baixar: list[str]) -> list[Parte]:
    partes = []
    for id_ in baixar:
        c = componentes.pegar(id_)
        partes.append(Parte(f"baixar:{id_}", f"Baixando {c.nome} ({c.tamanho()})",
                            bytes=c.bytes))
    partes += [Parte(e, NOMES[e]) for e in ETAPAS]
    return partes


@dataclass
class Tarefa:
    #: O vídeo da thumbnail: o vídeo único, ou, na montagem, o da pessoa (com o
    #: personagem, o do fundo).
    video: Path
    destino: Path
    edicao: OpcoesDeEdicao
    saida: saida_mod.OpcoesDeSaida
    previa_s: float | None = None
    montagem: Montagem | None = None
    #: Os componentes que quem usa aprovou e que baixam antes da edição.
    baixar: list[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    estado: str = "rodando"            # rodando | pronto | erro | cancelado
    etapa: str = "transcrevendo"
    fracao: float = 0.0
    detalhe: str = ""
    comeco: float = field(default_factory=time.monotonic)
    fim: float | None = None
    resultado: dict | None = None
    erro: str = ""
    cancelar: threading.Event = field(default_factory=threading.Event)
    versao: int = 0
    partes: list[Parte] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.partes:
            self.partes = _partes(self.baixar)
        if self.baixar:
            self.etapa = f"baixar:{self.baixar[0]}"

    def parte(self, id_: str) -> Parte:
        for p in self.partes:
            if p.id == id_:
                return p
        # uma etapa que não estava prevista ganha a sua barra, logo depois da última que começou
        p = Parte(id_, NOMES.get(id_, id_))
        k = max((i + 1 for i, q in enumerate(self.partes) if q.estado != "esperando"), default=0)
        self.partes.insert(k, p)
        return p

    def andar(self, etapa: str, fracao: float, detalhe: str = "") -> None:
        """A edição avisou: as partes antes desta acabaram (ou foram puladas)."""
        atual = self.parte(etapa)
        for p in self.partes:
            if p is atual:
                break
            p.acabar()
        atual.andar(fracao, detalhe)
        self.etapa, self.fracao = etapa, fracao
        if detalhe:
            self.detalhe = detalhe
        self.versao += 1

    def total(self) -> float:
        downloads = [p for p in self.partes if p.id.startswith("baixar:")]
        if self.etapa.startswith("baixar:"):
            todos = sum(p.bytes for p in downloads) or 1
            feitos = sum(p.bytes * p.fracao for p in downloads)
            return PESO_DOS_DOWNLOADS * feitos / todos
        a, b = PESOS.get(self.etapa, (0.0, 1.0))
        da_edicao = a + (b - a) * min(1.0, max(0.0, self.fracao))
        if not downloads:
            return da_edicao
        return PESO_DOS_DOWNLOADS + (1 - PESO_DOS_DOWNLOADS) * da_edicao

    def falta_s(self) -> float | None:
        """Quanto falta, pela velocidade do desenho (a etapa mais longa e mais regular)."""
        if self.estado != "rodando" or self.etapa != "desenhando" or self.fracao < 0.05:
            return None
        desenho = self.parte("desenhando")
        return desenho.falta_s() if desenho.comeco is not None else None

    def para_dict(self) -> dict:
        return {"id": self.id, "estado": self.estado, "etapa": self.etapa,
                "etapa_nome": NOMES.get(self.etapa, self.parte(self.etapa).nome),
                "fracao": round(self.total(), 4), "detalhe": self.detalhe,
                "falta_s": self.falta_s(), "resultado": self.resultado, "erro": self.erro,
                "decorrido_s": round((self.fim or time.monotonic()) - self.comeco, 1),
                "versao": self.versao, "partes": [p.para_dict() for p in self.partes]}


class Gerente:
    def __init__(self) -> None:
        self._trava = threading.Lock()
        self.tarefas: dict[str, Tarefa] = {}

    def ocupado(self) -> bool:
        return any(t.estado == "rodando" for t in self.tarefas.values())

    def iniciar(self, tarefa: Tarefa) -> Tarefa:
        with self._trava:
            if self.ocupado():
                raise Ocupado
            self.tarefas[tarefa.id] = tarefa
        threading.Thread(target=self._rodar, args=(tarefa,), daemon=True,
                         name=f"edicao-{tarefa.id}").start()
        return tarefa

    def _baixar(self, t: Tarefa) -> None:
        """Os downloads que quem usa aprovou, antes da edição, cada um com a sua barra."""
        for id_ in t.baixar:
            if t.cancelar.is_set():
                raise render.Cancelado
            componentes.baixar(id_, lambda f, texto, id_=id_: t.andar(f"baixar:{id_}", f, texto),
                               cancelar=t.cancelar.is_set)
            t.parte(f"baixar:{id_}").acabar()

    def _rodar(self, t: Tarefa) -> None:
        try:
            try:
                self._baixar(t)
            except InterruptedError as erro:
                raise render.Cancelado from erro
            r = render.editar(None if t.montagem is not None else t.video, t.destino,
                              t.edicao, t.saida, previa_s=t.previa_s, progresso=t.andar,
                              cancelar=t.cancelar.is_set, montagem=t.montagem)
            t.resultado = r.para_dict()
            for p in t.partes:
                p.acabar()
            t.estado, t.etapa, t.fracao = "pronto", "pronto", 1.0
        except render.Cancelado:
            t.estado, t.detalhe = "cancelado", "edição cancelada"
            for p in t.partes:
                if p.estado == "rodando":
                    p.acabar("cancelada")
            t.destino.unlink(missing_ok=True)
        except Exception as erro:
            # O Windows barrando uma biblioteca (o Whisper carrega na hora de transcrever)
            # vira o passo a passo para destravar.
            t.estado, t.erro = "erro", (bloqueio.explicar(erro) if bloqueio.bloqueado(erro)
                                        else f"{type(erro).__name__}: {erro}")
            t.detalhe = traceback.format_exc(limit=3)
            for p in t.partes:
                if p.estado == "rodando":
                    p.acabar("erro")
                    p.detalhe = t.erro
            t.destino.unlink(missing_ok=True)
        finally:
            t.fim = time.monotonic()
            t.versao += 1


__all__ = ["ETAPAS", "NOMES", "PESOS", "Gerente", "Ocupado", "Parte", "Tarefa"]
