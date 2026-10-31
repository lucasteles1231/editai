"""
Os cortes de silêncio: quais trechos do vídeo ficam.

Uma pausa maior que :data:`PAUSA_MAXIMA_S` vira um respiro curto
(:data:`RESPIRO_S`), e o começo e o fim do vídeo são aparados.

**A pausa é medida no áudio, não no tempo do Whisper** (:mod:`editor.fronteiras`). Ele erra
os dois lados da palavra: o fim sai cedo (cortar ali come a última sílaba), e o começo da palavra
que vem depois de uma pausa sai cedo também, às vezes com o silêncio inteiro dentro dela (cortar
ali deixa a pausa no vídeo). E às vezes as duas palavras parecem coladas, com o silêncio dentro
de uma delas: por isso também se procura, entre duas palavras "coladas", um silêncio engolido
maior que a pausa máxima.
"""
from __future__ import annotations

from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise

import numpy as np

from editor import fronteiras
from editor.transcricao import Palavra

#: Uma pausa maior que isto entre duas palavras vira corte.
PAUSA_MAXIMA_S = 0.45
#: Quanto do silêncio fica entre duas falas depois do corte (meio de cada lado).
RESPIRO_S = 0.15
#: O silêncio no começo de uma fala só conta se tiver pelo menos isto: sem pausa
#: antes (vídeo que já abre falando), a pausa achada seria o fechamento de uma
#: consoante dentro da primeira palavra, de 50 a 100 ms.
PAUSA_NO_COMECO_S = 0.15
#: Folga quando não há pausa clara (fala colada em música, por exemplo).
FOLGA_SEM_PAUSA_S = 0.06
#: Dois trechos mais próximos que isto viram um só.
JUNTAR_ABAIXO_DE_S = 0.05


@dataclass(frozen=True)
class Trecho:
    """Um pedaço do vídeo original que fica, em segundos."""

    ini: float
    fim: float

    @property
    def duracao(self) -> float:
        return self.fim - self.ini


def calcular(palavras: Sequence[Palavra], amostras: np.ndarray | None, taxa: int,
             duracao: float, *, pausa_maxima: float = PAUSA_MAXIMA_S,
             respiro: float = RESPIRO_S) -> list[Trecho]:
    """Os trechos a manter. Sem palavras, o vídeo fica inteiro."""
    ws = sorted(palavras, key=lambda p: p.inicio)
    if not ws or duracao <= 0:
        return [Trecho(0.0, max(0.0, duracao))]
    medida = (fronteiras.atividade(amostras, taxa)
              if amostras is not None and len(amostras) else None)
    # O que sai: o silêncio antes da primeira palavra, as pausas longas e o silêncio
    # depois da última. O que fica é o que sobra entre eles.
    fora = [(0.0, max(0.0, _comeco_real(ws[0], medida)))]
    for a, b in pairwise(ws):
        pausa = _pausa_entre(a, b, pausa_maxima, medida)
        if pausa:
            fora.append(pausa)
    fora.append((min(duracao, _fim_real(ws[-1], duracao, medida)), duracao))
    meio = respiro / 2
    fora = _unir(fora)
    trechos = [Trecho(max(0.0, ini - meio), min(duracao, fim + meio))
               for (_, ini), (fim, _) in pairwise(fora)]
    return _juntar(trechos)


def _pausa_entre(a: Palavra, b: Palavra, pausa_maxima: float,
                 medida: fronteiras.Atividade | None) -> tuple[float, float] | None:
    """O silêncio a cortar entre duas palavras seguidas, ou ``None``."""
    vao = b.inicio - a.fim
    if medida is None:
        if vao > pausa_maxima:
            return a.fim + FOLGA_SEM_PAUSA_S, b.inicio - FOLGA_SEM_PAUSA_S
        return None
    if vao > pausa_maxima:
        achada = fronteiras.entre(medida, a, b)
        if achada is None:
            return a.fim + FOLGA_SEM_PAUSA_S, b.inicio - FOLGA_SEM_PAUSA_S
        return achada.fim_da_fala, achada.comeco_da_fala
    # O Whisper diz que estão coladas, mas pode ter posto a pausa dentro de uma delas.
    # A janela vai do meio da primeira ao fim da segunda; o fechamento de uma
    # consoante não passa de 100 ms, então nada dentro da palavra chega à pausa máxima.
    achada = fronteiras.pausa(medida, (a.inicio + a.fim) / 2, b.fim)
    if achada and achada.duracao > pausa_maxima:
        return achada.fim_da_fala, achada.comeco_da_fala
    return None


def _comeco_real(palavra: Palavra, medida: fronteiras.Atividade | None) -> float:
    """Onde o som da primeira palavra começa."""
    achada = fronteiras.entre(medida, None, palavra) if medida else None
    if achada and achada.duracao >= PAUSA_NO_COMECO_S:
        return achada.comeco_da_fala
    return palavra.inicio - FOLGA_SEM_PAUSA_S


def _fim_real(palavra: Palavra, duracao: float, medida: fronteiras.Atividade | None) -> float:
    """Onde o som da última palavra acaba."""
    achada = fronteiras.entre(medida, palavra, None, duracao) if medida else None
    return achada.fim_da_fala if achada else palavra.fim + FOLGA_SEM_PAUSA_S


def _unir(fora: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Os silêncios em ordem e sem sobreposição: o mesmo silêncio engolido pode ser
    achado pelos dois pares de palavras em volta dele."""
    saida: list[tuple[float, float]] = []
    for ini, fim in sorted(fora):
        if saida and ini <= saida[-1][1]:
            saida[-1] = (saida[-1][0], max(saida[-1][1], fim))
        else:
            saida.append((ini, max(ini, fim)))
    return saida


def _juntar(trechos: list[Trecho]) -> list[Trecho]:
    saida: list[Trecho] = []
    for t in sorted(trechos, key=lambda t: t.ini):
        if t.duracao <= 0:
            continue
        if saida and t.ini - saida[-1].fim < JUNTAR_ABAIXO_DE_S:
            saida[-1] = Trecho(saida[-1].ini, max(saida[-1].fim, t.fim))
        else:
            saida.append(t)
    return saida


def cruzar(trechos: Sequence[Trecho], intervalos: Sequence[tuple[float, float]]) -> list[Trecho]:
    """O que fica nos dois: os trechos sem os silêncios, só dentro dos intervalos (as frases
    que a duração escolhida deixou, :mod:`editor.duracao`)."""
    saida = [Trecho(max(t.ini, a), min(t.fim, b)) for t in trechos for a, b in intervalos
             if min(t.fim, b) > max(t.ini, a)]
    return _juntar(saida)


class Linha:
    """O mapa do tempo original para o tempo do vídeo editado."""

    def __init__(self, trechos: Sequence[Trecho]):
        self.trechos = list(trechos)
        self._inicios = [t.ini for t in self.trechos]
        self._na_saida, acumulado = [], 0.0
        for t in self.trechos:
            self._na_saida.append(acumulado)
            acumulado += t.duracao
        self.duracao = acumulado

    def _trecho_de(self, t: float) -> int | None:
        i = bisect_right(self._inicios, t) - 1
        if i < 0 or t > self.trechos[i].fim:
            return None
        return i

    def para_saida(self, t: float) -> float | None:
        """O instante de saída de ``t``, ou ``None`` se ``t`` foi cortado."""
        i = self._trecho_de(t)
        return None if i is None else self._na_saida[i] + (t - self.trechos[i].ini)

    def fronteiras(self) -> list[float]:
        """Os instantes de saída em que um trecho emenda no seguinte (onde houve corte)."""
        return list(self._na_saida[1:])

    def para_origem(self, t: float) -> float:
        """O instante do vídeo original que vira ``t`` na saída (o inverso de
        :meth:`para_saida`). Fora da linha, prende no começo ou no fim."""
        if not self.trechos:
            return t
        i = max(0, bisect_right(self._na_saida, t) - 1)
        tr = self.trechos[i]
        return min(tr.fim, tr.ini + max(0.0, t - self._na_saida[i]))

    def prender(self, t: float) -> float:
        """Como :meth:`para_saida`, mas um instante cortado vai para a borda mais próxima."""
        dentro = self.para_saida(t)
        if dentro is not None:
            return dentro
        i = bisect_right(self._inicios, t) - 1
        if i < 0:
            return 0.0
        if i + 1 < len(self.trechos) and (self.trechos[i + 1].ini - t) < (t - self.trechos[i].fim):
            return self._na_saida[i + 1]
        return self._na_saida[i] + self.trechos[i].duracao

    @property
    def cortes(self) -> list[float]:
        """Os instantes de saída em que houve corte (onde dois trechos se encontram)."""
        return self._na_saida[1:]

    def palavras(self, palavras: Sequence[Palavra]) -> list[Palavra]:
        """As palavras no tempo de saída; as que caíram inteiras num corte somem.

        Uma palavra que atravessa um corte é a que ganhou do Whisper o silêncio de
        antes: o som dela está onde ela termina, e é lá que ela começa na saída — senão
        a legenda acenderia a palavra ainda na frase anterior.
        """
        saida = []
        for p in palavras:
            i, j = self._trecho_de(p.inicio), self._trecho_de(p.fim)
            if i is None and j is None:
                i = j = self._trecho_de((p.inicio + p.fim) / 2)
                if i is None:
                    continue
            if j is None:
                j = i
            if i is None or i != j:
                i = j
            a = self.para_saida(max(p.inicio, self.trechos[i].ini))
            b = self.para_saida(min(p.fim, self.trechos[j].fim))
            if b <= a:
                b = a + 0.05
            saida.append(Palavra(p.texto, round(a, 3), round(b, 3), p.prob))
        return saida


__all__ = ["PAUSA_MAXIMA_S", "RESPIRO_S", "Linha", "Trecho", "calcular", "cruzar"]
