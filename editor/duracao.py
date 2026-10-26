"""
A duração escolhida no passo 1: quanto o vídeo deve durar. O que passar, a IA escolhe as frases
que ficam e o editor corta o resto, como quem faz um Short de um vídeo maior.

- **As escolhas:** ``"auto"`` (só sai o que passar do limite da plataforma marcada), ``"tudo"``
  (nada da fala sai, só os silêncios) ou os segundos (``"30"``).
- **O tempo é médio:** ±15% (:data:`FOLGA`), porque o corte cai sempre entre frases. No Auto,
  o vídeo fica com até 95% do limite, e nunca passa dele.
- **As frases** saem das palavras: fecham na pontuação final e nas pausas longas. Cada uma vale
  o que dura no vídeo já sem os silêncios.
- **Quem escolhe** é a IA, num pedido só (com um conserto), com as frases numeradas. Ela pode
  começar mais adiante, para abrir com um gancho, mas não troca a ordem nem corta uma frase
  no meio. Sem a IA, o corte é no fim, na última frase que cabe.
- **O corte** cai no meio da pausa entre duas frases. Os trechos escolhidos cruzam com os dos
  silêncios (:func:`cortes.cruzar`), e daí a linha do tempo é a de sempre: a legenda, o zoom, as
  cenas, os cartões e as camadas da montagem seguem o corte sem saber dele.
- **As palavras das frases que saíram saem da legenda** (:meth:`Selecao.sem_as_de_fora`): o
  Whisper adianta o começo da palavra depois de uma pausa, e no primeiro vídeo de verdade o
  "Da" da frase seguinte começava 30 ms antes do corte e aparecia no fim da legenda.
- **Uma frase que retoma a anterior** ("Por isso", "Ou seja", "É assim", "Esses…") só fica com
  a anterior: no primeiro corte de verdade (3 min para 45 s), a IA deixou "esses sinais" sem os
  satélites e "Ou seja" sem a relatividade. A conferência acusa e pede o conserto.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field

from editor import cortes, ia
from editor.transcricao import Palavra

logger = logging.getLogger(__name__)

#: A folga do tempo escolhido, para mais ou para menos.
FOLGA = 0.15
#: No Auto, o vídeo que passa do limite fica com uns 95% dele.
MARGEM_DO_AUTO = 0.95
#: As escolhas que a página oferece, em segundos (o terminal aceita qualquer número entre os
#: extremos).
ESCOLHAS = (15, 20, 30, 45, 60, 90, 120, 180, 300, 600)
SEGUNDOS_MINIMOS, SEGUNDOS_MAXIMOS = 5, 3600
#: O limite de cada plataforma, em segundos (``None``: sem limite prático). Pesquisado em
#: 25/10/2026, em guias de 2026 (as páginas oficiais não apareceram na busca):
#: - o Shorts vai até 3 min, e passou disso vira vídeo comum;
#: - o Instagram aceita Reels de até 20 min, mas não recomenda a quem não segue o perfil os de
#:   mais de 3;
#: - o TikTok grava até 10 min no app (enviando, até 60, ainda não para todas as contas);
#: - o YouTube vai até 12 h (15 min numa conta não verificada).
LIMITES: dict[str, int | None] = {"youtube": None, "shorts": 180, "reels": 180, "tiktok": 600}
#: Uma pausa maior que isto entre duas palavras fecha a frase, mesmo sem pontuação.
PAUSA_DE_FRASE_S = 0.7
#: Uma frase com mais palavras que isto fecha na próxima vírgula.
PALAVRAS_POR_FRASE = 40
FIM_DE_FRASE = (".", "?", "!", "…")
#: Os começos que retomam a frase anterior: sem ela, a frase fica sem sentido.
RETOMAM = ("por isso", "ou seja", "então", "assim", "é assim", "foi assim", "com isso", "daí",
           "dessa forma", "desse jeito", "nesse caso", "além disso", "mas", "porém", "só que",
           "isso", "isto", "esse", "essa", "esses", "essas", "este", "esta", "estes", "estas",
           "ele", "ela", "eles", "elas", "lá", "aí", "nele", "nela", "também")

SISTEMA = """Você edita vídeos curtos: escolhe quais frases de uma fala ficam para o vídeo caber no
tempo, sem perder o sentido. Responda só com o JSON pedido."""


class DuracaoInvalida(ValueError):
    """A escolha não é "auto", "tudo" nem um número de segundos."""


def ler(escolha) -> str | float:
    """``"auto"``, ``"tudo"`` ou os segundos. Levanta :class:`DuracaoInvalida`."""
    texto = str(escolha if escolha is not None else "auto").strip().lower()
    if texto in ("auto", "tudo"):
        return texto
    try:
        segundos = float(texto.removesuffix("s").strip().replace(",", "."))
    except ValueError as erro:
        raise DuracaoInvalida(f'a duração é "auto", "tudo" ou os segundos (veio "{escolha}")'
                              ) from erro
    if not SEGUNDOS_MINIMOS <= segundos <= SEGUNDOS_MAXIMOS:
        raise DuracaoInvalida(f"a duração vai de {SEGUNDOS_MINIMOS} a {SEGUNDOS_MAXIMOS} segundos")
    return segundos


def limite_das(plataformas: Sequence[str]) -> float | None:
    """O menor limite entre as plataformas marcadas (``None``: nenhuma tem limite)."""
    valores = [v for v in (LIMITES.get(p) for p in plataformas) if v]
    return float(min(valores)) if valores else None


@dataclass(frozen=True)
class Alvo:
    """Quanto o vídeo deve ficar, e a faixa aceita."""

    segundos: float
    minimo: float
    maximo: float


def alvo(escolha, limite: float | None, total: float) -> Alvo | None:
    """O alvo para um vídeo de ``total`` segundos, ou ``None`` se nada precisa sair."""
    e = ler(escolha)
    if e == "tudo":
        return None
    if e == "auto":
        if limite is None or total <= limite:
            return None
        s = limite * MARGEM_DO_AUTO
        return Alvo(s, s * (1 - FOLGA), float(limite))
    if total <= e * (1 + FOLGA):
        return None
    return Alvo(e, e * (1 - FOLGA), e * (1 + FOLGA))


@dataclass
class Frase:
    k: int
    texto: str
    #: No vídeo original: o começo da primeira palavra e o fim da última.
    ini: float
    fim: float
    #: Onde ela começa e termina para o corte: no meio da pausa com a vizinha.
    corte_ini: float = 0.0
    corte_fim: float = 0.0
    #: Quanto ela dura no vídeo editado (já sem os silêncios).
    segundos: float = 0.0


def _no_editado(linha: cortes.Linha, a: float, b: float) -> float:
    return sum(max(0.0, min(b, t.fim) - max(a, t.ini)) for t in linha.trechos)


def frases(palavras: Sequence[Palavra], linha: cortes.Linha, duracao: float) -> list[Frase]:
    """As frases da fala, em ordem, com onde cada uma pode ser cortada."""
    ws = sorted(palavras, key=lambda p: p.inicio)
    grupos: list[list[Palavra]] = []
    atual: list[Palavra] = []
    for i, w in enumerate(ws):
        atual.append(w)
        prox = ws[i + 1] if i + 1 < len(ws) else None
        fecha = w.texto.rstrip("\"'”»)").endswith(FIM_DE_FRASE)
        pausa = prox is not None and prox.inicio - w.fim > PAUSA_DE_FRASE_S
        longa = len(atual) >= PALAVRAS_POR_FRASE and w.texto.endswith((",", ";", ":"))
        if prox is None or fecha or pausa or longa:
            grupos.append(atual)
            atual = []
    lista = [Frase(k, " ".join(w.texto for w in g), g[0].inicio, g[-1].fim)
             for k, g in enumerate(grupos)]
    for k, f in enumerate(lista):
        f.corte_ini = 0.0 if k == 0 else (lista[k - 1].fim + f.ini) / 2
        f.corte_fim = duracao if k == len(lista) - 1 else (f.fim + lista[k + 1].ini) / 2
        f.segundos = round(_no_editado(linha, f.corte_ini, f.corte_fim), 2)
    return lista


@dataclass
class Selecao:
    """O que a duração escolhida decidiu."""

    escolha: str
    alvo: float | None = None
    #: A duração do vídeo sem os silêncios, antes e depois da escolha das frases.
    antes: float = 0.0
    depois: float = 0.0
    #: Os intervalos do vídeo original que ficam (``None``: nada saiu).
    manter: list[tuple[float, float]] | None = None
    fora: list[Frase] = field(default_factory=list)
    #: Quem escolheu: "gemini", "falsa", "fim" (o corte no fim, sem a IA) ou "" (nada saiu).
    por: str = ""
    aviso: str = ""
    pedidos: int = 0

    def sem_as_de_fora(self, palavras: Sequence[Palavra]) -> list[Palavra]:
        """As palavras sem as das frases que saíram (a legenda e o plano usam estas)."""
        if not self.fora:
            return list(palavras)
        return [w for w in palavras
                if not any(f.ini <= w.inicio and w.fim <= f.fim for f in self.fora)]

    def para_json(self) -> dict:
        return {"escolha": self.escolha,
                "alvo": round(self.alvo, 1) if self.alvo is not None else None,
                "antes": round(self.antes, 2), "depois": round(self.depois, 2), "por": self.por,
                "aviso": self.aviso, "pedidos": self.pedidos,
                "fora": [{"texto": f.texto, "inicio": round(f.ini, 2), "fim": round(f.fim, 2),
                          "segundos": f.segundos} for f in self.fora]}


def _s(segundos: float) -> str:
    return f"{segundos:.1f}".replace(".", ",") + " s"


def esquema() -> dict:
    return {"type": "object", "properties": {
        "manter": {"type": "array", "items": {"type": "integer"}},
        "porque": {"type": "string"}}, "required": ["manter", "porque"]}


def montar_pedido(lista: Sequence[Frase], a: Alvo, *, tema: str = "") -> str:
    linhas = "\n".join(f"- {f.k} ({_s(f.segundos)}): {f.texto}" for f in lista)
    total = sum(f.segundos for f in lista)
    sobre = f"O tema do vídeo: {tema}\n\n" if tema else ""
    faixa = f"entre {a.minimo:.0f} e {a.maximo:.0f} s"
    return f"""{sobre}A fala, frase a frase, com quanto cada uma dura no vídeo:
{linhas}

O vídeo tem {total:.0f} s e precisa ficar com uns {a.segundos:.0f} s ({faixa}).

Escolha as frases que ficam:
- inteiras e na ordem em que foram ditas: devolva só os números;
- o vídeo pode começar numa frase mais adiante, se ela prende mais quem assiste;
- nenhuma ideia pela metade: se uma frase depende da anterior, as duas ficam ou saem juntas.
  Uma frase que começa retomando a anterior ("por isso", "ou seja", "é assim", "esses", "isso",
  "ele") só fica se a anterior ficar;
- termine numa frase que feche a ideia;
- some as durações: o total tem de ficar {faixa}.

"manter": os números das frases que ficam, em ordem.
"porque": numa frase, o que saiu e por quê."""


def _soma(lista: Sequence[Frase], ids: Sequence[int]) -> float:
    return sum(lista[i].segundos for i in ids)


def _retoma(texto: str) -> str:
    """O começo que retoma a frase anterior ("Por isso"), ou ""."""
    t = texto.lower().lstrip("\"'“«(-— ")
    return next((r for r in sorted(RETOMAM, key=len, reverse=True)
                 if t.startswith(r) and (len(t) == len(r) or not t[len(r)].isalnum())), "")


def soltas(lista: Sequence[Frase], ids: Sequence[int]) -> list[tuple[int, str]]:
    """As frases escolhidas que retomam a anterior sem ela ter ficado. A primeira da fala
    pode: é o jeito de quem gravou."""
    ficam = set(ids)
    return [(i, r) for i in ids
            if i > 0 and (i - 1) not in ficam and (r := _retoma(lista[i].texto))]


def conferir(resposta, lista: Sequence[Frase], a: Alvo) -> tuple[list[int], list[str]]:
    """As frases que a IA escolheu (as que existem, em ordem) e o que precisa de conserto."""
    brutos = resposta.get("manter") if isinstance(resposta, dict) else None
    ids = sorted({i for i in brutos or [] if isinstance(i, int) and not isinstance(i, bool)
                  and 0 <= i < len(lista)})
    if not ids:
        return [], ['não veio nenhuma frase em "manter"']
    problemas = []
    total = _soma(lista, ids)
    if total > a.maximo:
        problemas.append(f"as frases escolhidas somam {_s(total)} e passam de {a.maximo:.0f} s")
    elif total < a.minimo:
        problemas.append(f"as frases escolhidas somam {_s(total)} e ficam abaixo de "
                         f"{a.minimo:.0f} s")
    problemas += [f'a frase {i} começa com "{r}" e depende da {i - 1}, que saiu: mantenha as '
                  "duas ou tire as duas" for i, r in soltas(lista, ids)]
    return ids, problemas


def cortar_no_fim(lista: Sequence[Frase], a: Alvo) -> list[int]:
    """As frases do começo até a última que cabe (pelo menos a primeira)."""
    ids: list[int] = []
    total = 0.0
    for f in lista:
        if ids and total + f.segundos > a.maximo:
            break
        ids.append(f.k)
        total += f.segundos
    return ids


def _aparar(lista: Sequence[Frase], ids: list[int], maximo: float) -> list[int]:
    """Tira as últimas escolhidas até caber (pelo menos uma fica)."""
    ids = list(ids)
    while len(ids) > 1 and _soma(lista, ids) > maximo:
        ids.pop()
    return ids


def _pela_ia(lista: Sequence[Frase], a: Alvo, tema: str, transporte
             ) -> tuple[list[int], int, str]:
    """As frases que a IA escolheu, quantos pedidos foram e o aviso (o erro, sem frase)."""
    pedido = montar_pedido(lista, a, tema=tema)
    gasto: list[str] = []
    try:
        resposta, _modelo = ia.perguntar_json(SISTEMA, pedido, esquema(), temperatura=0.3,
                                              transporte=transporte, gasto=gasto)
    except ia.ErroDaIA as erro:
        return [], len(gasto), str(erro)
    ids, problemas = conferir(resposta, lista, a)
    if problemas:
        logger.info("conserto da escolha das frases: %s", " | ".join(problemas))
        conserto = (pedido + "\n\nA RESPOSTA ANTERIOR TEVE ESTES PROBLEMAS. Mande o JSON inteiro "
                    "de novo, corrigido:\n" + "\n".join(f"- {p}" for p in problemas)
                    + "\n\nA resposta anterior:\n" + json.dumps(resposta, ensure_ascii=False))
        try:
            resposta2, _modelo = ia.perguntar_json(SISTEMA, conserto, esquema(), temperatura=0.2,
                                                   transporte=transporte, gasto=gasto)
            ids2, problemas2 = conferir(resposta2, lista, a)
            if ids2 and len(problemas2) <= len(problemas):
                ids = ids2
        except ia.ErroDaIA:
            logger.info("o conserto da escolha não veio; fica a primeira")
    if not ids:
        return [], len(gasto), "a resposta não trouxe nenhuma frase"
    aviso = ""
    if _soma(lista, ids) > a.maximo:
        ids = _aparar(lista, ids, a.maximo)
        aviso = "A IA passou do tempo: as últimas frases que ela escolheu saíram para caber."
    elif _soma(lista, ids) < a.minimo:
        aviso = (f"A IA deixou {_s(_soma(lista, ids))}, abaixo dos {a.minimo:.0f} s da faixa "
                 "pedida.")
    return ids, len(gasto), aviso


def _juntar_vizinhas(intervalos: list[tuple[float, float]]) -> list[tuple[float, float]]:
    saida: list[tuple[float, float]] = []
    for a, b in intervalos:
        if saida and a <= saida[-1][1] + 1e-6:
            saida[-1] = (saida[-1][0], max(saida[-1][1], b))
        else:
            saida.append((a, b))
    return saida


def escolher(palavras: Sequence[Palavra], linha: cortes.Linha, duracao: float, *,
             escolha="auto", limite: float | None = None, tema: str = "",
             transporte=None) -> Selecao:
    """As frases que ficam para o vídeo caber na duração escolhida."""
    sel = Selecao(str(escolha or "auto"), antes=linha.duracao, depois=linha.duracao)
    a = alvo(escolha, limite, linha.duracao)
    if a is None or not palavras:
        return sel
    sel.alvo = a.segundos
    lista = frases(palavras, linha, duracao)
    if len(lista) < 2:
        sel.aviso = "A fala é uma frase só, mais longa que o tempo escolhido: nada saiu dela."
        return sel
    if ia.falsa():
        ids, sel.por = cortar_no_fim(lista, a), "falsa"
    elif ia.ligada():
        ids, sel.pedidos, aviso = _pela_ia(lista, a, tema, transporte)
        sel.por = "gemini"
        if not ids:
            ids, sel.por = cortar_no_fim(lista, a), "fim"
            sel.aviso = (f"A IA não escolheu ({aviso}): o vídeo foi cortado no fim, na última "
                         "frase que coube.")
        else:
            sel.aviso = aviso
    else:
        ids, sel.por = cortar_no_fim(lista, a), "fim"
        sel.aviso = "Sem IA, o vídeo foi cortado no fim, na última frase que coube."
    ficam = set(ids)
    sel.manter = _juntar_vizinhas([(lista[i].corte_ini, lista[i].corte_fim) for i in ids])
    sel.fora = [f for f in lista if f.k not in ficam]
    sel.depois = round(_soma(lista, ids), 2)
    return sel


__all__ = ["ESCOLHAS", "FOLGA", "LIMITES", "RETOMAM", "Alvo", "DuracaoInvalida", "Frase", "Selecao",
           "alvo", "conferir", "cortar_no_fim", "escolher", "esquema", "frases", "ler",
           "limite_das", "montar_pedido", "soltas"]
