"""
O começo e o fim reais da fala em volta de uma pausa, medidos no som e não no Whisper.

O Whisper erra as duas pontas da palavra. No gabarito marcado à mão
(``ferramentas/marcar_palavras.py``), o fim dele cai antes do fim do som em 20 de 21 palavras
(come a cauda da última sílaba, até 370 ms), e o começo erra de 250 ms para trás a 420 ms para
frente (às vezes ele põe a palavra inteira dentro do silêncio que vem antes dela).

**Como:**

1. **A atividade:** a energia em janelas de 5 ms a cada 1 ms, em duas faixas (:data:`FAIXAS_HZ`):
   a da voz, de 150 Hz a 4 kHz, e a de cima. Abaixo de 150 Hz fica o ronco (o ar, a mesa, o
   prédio), que nas pausas das gravações reais chega a passar a própria fala nessa faixa e
   partia a pausa ao meio. O "s", o "f" e o "x" quase não têm energia embaixo; só a faixa de cima
   os vê.
2. **A pausa:** onde as duas faixas estão quietas (:data:`LIMIAR_PAUSA_DB` acima do fundo, ou
   :data:`ABAIXO_DO_PICO_DB` abaixo do mais alto), pela que mais cobre o vão do Whisper entre as
   duas palavras, puxado para depois (:data:`ANTES_S`, :data:`DEPOIS_S`): o Whisper sai cedo
   dos dois lados. A pausa vale inteira, mesmo passando do vão: quando ele põe a palavra dentro
   do silêncio, o começo dela ainda é pausa. **Um respiro ou um estalo não partem a pausa:** a
   pausa é achada na energia passada por uma mediana de :data:`MEDIANA_S`, que apaga o estalo, e
   entre dois pedaços quietos, o que nunca chega à fala (:data:`FALA_ABAIXO_DO_PICO_DB` do mais
   alto e :data:`FALA_ACIMA_DA_PAUSA_DB` acima do limiar da pausa) é parte dela. **Sem pausa**
   (a vírgula na fala corrida, que o eco da sala enche), fica o tempo do Whisper: procurar o vale
   ali achava também o fechamento do "t" dentro da palavra, e errava mais do que acertava.
3. **As bordas:** de cada lado, o fundo é medido só nos :data:`VIZINHANCA_S` de pausa colados à
   fala, e a borda é onde a atividade chega a :data:`BORDA_DB` dele. Assim a cauda que some
   devagar (o "ã" de "manhã") fica na fala; e um respiro ou um silêncio digital (zeros, de um
   portão de ruído) mais longe na pausa não puxam a borda para lá.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from editor.transcricao import Palavra

#: A energia: janelas de 5 ms a cada 1 ms (com 10 ms, a borda borrava para fora: no gabarito,
#: 64% dentro de 30 ms, contra 72%).
JANELA_S = 0.005
PASSO_S = 0.001
#: As faixas: a da voz, sem o ronco grave, e a de cima, onde o "s", o "f" e o "x" aparecem. Cada
#: borda é uma rampa de cosseno de :data:`RAMPA` da frequência para cada lado: o corte seco
#: espalhava o som por centenas de ms (cai com 1/t), e a ponta do trecho medido vazava para
#: dentro das pausas.
FAIXAS_HZ = ((150, 4_000), (4_000, None))
RAMPA = 0.25
#: É pausa o que fica abaixo de :data:`LIMIAR_PAUSA_DB` acima do fundo, ou de
#: :data:`ABAIXO_DO_PICO_DB` abaixo do mais alto (o fundo de um vídeo com silêncio digital fica em
#: −140 dB e não diz nada); a pausa tem pelo menos :data:`PAUSA_MINIMA_S`.
LIMIAR_PAUSA_DB = 10.0
ABAIXO_DO_PICO_DB = 30.0
#: Uma faixa cujo mais alto fica a menos disto do fundo não diz nada e fica de fora. Sem
#: contraste na faixa da voz, não há pausa: toda fala tem energia ali, e num trecho só de fala o
#: fundo medido é a própria fala (tudo viraria pausa).
CONTRASTE_MINIMO_DB = 20.0
PAUSA_MINIMA_S = 0.04
#: É fala o que chega a isto do mais alto e passa isto do limiar da pausa (numa gravação com o
#: fundo alto, a 25 dB do mais alto ainda é o chiado); o resto, um respiro, fica na pausa.
FALA_ABAIXO_DO_PICO_DB = 25.0
FALA_ACIMA_DA_PAUSA_DB = 6.0
#: A pausa é achada na energia passada por esta mediana, que apaga um estalo de até a metade.
MEDIANA_S = 0.031
#: A borda: onde a atividade chega a isto do fundo medido nos :data:`VIZINHANCA_S` de pausa
#: colados à fala.
BORDA_DB = 8.0
VIZINHANCA_S = 0.2
ABAIXO_DA_PALAVRA_DB = 40.0
#: O fundo nunca fica mais que isto abaixo do mais alto: num silêncio digital (zeros), o fundo
#: iria a −140 dB, e qualquer sopro contaria como fala.
FAIXA_DB = 70.0
#: O vão do Whisper entre as duas palavras, puxado para depois: é onde a pausa é procurada.
ANTES_S = 0.1
DEPOIS_S = 0.3
#: Quanto a pausa pode passar do vão, dos dois lados.
MARGEM_S = 1.0
#: A atividade é medida em blocos deste tamanho, com esta sobra de cada lado (o filtro das
#: faixas, feito pela FFT, borra a ponta do bloco) e mais esta folga de zeros.
BLOCO_S = 10.0
SOBRA_S = 0.2


@dataclass(frozen=True)
class Pausa:
    """Uma pausa entre duas falas, em segundos."""

    fim_da_fala: float
    comeco_da_fala: float

    @property
    def duracao(self) -> float:
        return self.comeco_da_fala - self.fim_da_fala


@dataclass(frozen=True)
class Atividade:
    """A energia de cada faixa (:data:`FAIXAS_HZ`) a cada :data:`PASSO_S`, do áudio inteiro,
    medida uma vez: a crua, para as bordas, e a passada pela mediana, para achar a pausa.

    Medir de novo a cada pausa custava uma FFT de uns 3 s por par de palavras, e o corte de
    silêncio procura a pausa engolida em todos os pares.
    """

    cruas: tuple[np.ndarray, ...]
    lisas: tuple[np.ndarray, ...]
    #: Os segundos entre uma janela e a seguinte.
    passo_s: float

    def indice(self, t: float) -> int:
        return int(np.clip(round(t / self.passo_s), 0, len(self.cruas[0])))


def atividade(x: np.ndarray, taxa: int) -> Atividade:
    """A :class:`Atividade` do áudio ``x`` (mono), em blocos de :data:`BLOCO_S` (a memória não
    cresce com o vídeo)."""
    janela, passo = max(1, int(JANELA_S * taxa)), max(1, int(PASSO_S * taxa))
    quadros = max(0, (len(x) - janela) // passo + 1)
    cruas = [np.full(quadros, -140.0) for _ in FAIXAS_HZ]
    bloco = max(passo, int(BLOCO_S * taxa) // passo * passo)
    sobra = int(SOBRA_S * taxa) // passo * passo
    for ini in range(0, quadros * passo, bloco):
        de = max(0, ini - sobra)
        trecho = np.asarray(x[de:min(len(x), ini + bloco + sobra + janela)], dtype=np.float64)
        k, n = ini // passo, min(bloco // passo, quadros - ini // passo)
        pulo = (ini - de) // passo
        for crua, db in zip(cruas, _faixas(trecho, taxa, janela, passo), strict=True):
            crua[k:k + n] = db[pulo:pulo + n]
    lisas = tuple(_mediana(crua, int(MEDIANA_S / PASSO_S)) for crua in cruas)
    return Atividade(tuple(cruas), lisas, passo / taxa)


def _energia(x: np.ndarray, janela: int, passo: int) -> np.ndarray:
    acumulada = np.concatenate([[0.0], np.cumsum(x * x)])
    k = np.arange(0, len(x) - janela + 1, passo)
    return 10 * np.log10((acumulada[k + janela] - acumulada[k]) / janela + 1e-14)


def _faixas(trecho: np.ndarray, taxa: int, janela: int, passo: int) -> list[np.ndarray]:
    # zeros dos dois lados: a FFT é circular, e o fim do trecho daria a volta para o começo. E
    # o tamanho vai à potência de 2 seguinte: com um fator primo grande, a FFT ficava 5x mais lenta
    folga = int(SOBRA_S * taxa)
    tamanho = 1 << (len(trecho) + 2 * folga - 1).bit_length()
    espectro = np.fft.rfft(np.pad(trecho, folga), tamanho)
    hz = np.fft.rfftfreq(tamanho, 1 / taxa)
    return [_energia(np.fft.irfft(espectro * _ganho(hz, de) * (1 - _ganho(hz, ate)),
                                  tamanho)[folga:folga + len(trecho)], janela, passo)
            for de, ate in FAIXAS_HZ]


def _ganho(hz: np.ndarray, corte: float | None) -> np.ndarray:
    """De 0 a 1 em volta de ``corte``, numa rampa de cosseno (``None``: nunca sobe)."""
    if corte is None:
        return np.zeros_like(hz)
    de, ate = corte * (1 - RAMPA), corte * (1 + RAMPA)
    return 0.5 - 0.5 * np.cos(np.pi * np.clip((hz - de) / (ate - de), 0, 1))


def _mediana(db: np.ndarray, n: int, *, bloco: int = 65_536) -> np.ndarray:
    """A mediana móvel de ``n`` janelas, em blocos (de uma vez, um vídeo de 10 min pedia
    150 MB só para isso)."""
    if not len(db):
        return db.copy()
    metade = n // 2
    largo = np.pad(db, metade, mode="edge")
    return np.concatenate([
        np.median(np.lib.stride_tricks.sliding_window_view(
            largo[ini:ini + bloco + 2 * metade], 2 * metade + 1), axis=1)
        for ini in range(0, len(db), bloco)])


def _fundo(db: np.ndarray) -> float:
    """O percentil 5, sem o silêncio digital (os zeros de um portão de ruído): o fundo é o da
    sala, que se ouve antes de o portão fechar. Sem sala nenhuma (só fala e zeros, como numa voz
    gerada), o fundo são os zeros."""
    pico = float(db.max())
    som = db[db > pico - FAIXA_DB]
    if len(som) and pico - float(np.percentile(som, 5)) >= CONTRASTE_MINIMO_DB:
        return float(np.percentile(som, 5))
    return float(np.percentile(db, 5))


def _quieta(db: np.ndarray, fundo: float, acima: float) -> np.ndarray:
    """Onde a faixa está a menos de ``acima`` dB do fundo (que nunca fica mais que
    :data:`FAIXA_DB` abaixo do mais alto)."""
    return db < max(fundo, float(db.max()) - FAIXA_DB) + acima


def _corridas(mascara: np.ndarray) -> list[tuple[int, int]]:
    """Os trechos seguidos de ``True``, como ``(início, fim)`` com o fim exclusivo."""
    bordas = np.flatnonzero(np.diff(np.concatenate([[0], mascara.astype(np.int8), [0]])))
    return list(zip(bordas[::2], bordas[1::2], strict=True))


def pausa(medida: Atividade, de: float, ate: float) -> Pausa | None:
    """A pausa entre ``de`` e ``ate`` (segundos), com as bordas no som; ``None`` sem pausa."""
    k0, k1 = medida.indice(de - MARGEM_S), medida.indice(ate + MARGEM_S)
    a, b = medida.indice(de) - k0, medida.indice(ate) - k0
    if k1 - k0 < 3 or b <= a:
        return None
    uteis = [i for i, lisa in enumerate(medida.lisas)
             if float(lisa[k0:k1].max()) - _fundo(lisa[k0:k1]) >= CONTRASTE_MINIMO_DB]
    if 0 not in uteis:
        return None
    cruas = [medida.cruas[i][k0:k1] for i in uteis]
    lisas = [medida.lisas[i][k0:k1] for i in uteis]
    limiares = [max(_fundo(lisa) + LIMIAR_PAUSA_DB, float(lisa.max()) - ABAIXO_DO_PICO_DB)
                for lisa in lisas]
    fala = np.any([lisa >= max(float(lisa.max()) - FALA_ABAIXO_DO_PICO_DB,
                               limiar + FALA_ACIMA_DA_PAUSA_DB)
                   for lisa, limiar in zip(lisas, limiares, strict=True)], axis=0)
    achada = _escolher(np.all([lisa < limiar for lisa, limiar in zip(lisas, limiares, strict=True)],
                              axis=0), fala, a, b, int(PAUSA_MINIMA_S / PASSO_S))
    if achada is None:
        return None
    c, f = achada

    # as bordas: de cada lado, da fala para dentro da pausa, até a atividade chegar perto do
    # fundo medido ali do lado. O fim é o começo da primeira janela calma (o som acabou ali); o
    # começo, o fim da última
    vizinhanca = int(VIZINHANCA_S / PASSO_S)
    depois_da_fala = _calmas(cruas, c, min(f, c + vizinhanca), slice(max(0, c - vizinhanca), c))
    antes_da_fala = _calmas(cruas, max(c, f - vizinhanca), f, slice(f, f + vizinhanca))
    fim_da_fala = depois_da_fala[0] if len(depois_da_fala) else c
    comeco_da_fala = antes_da_fala[-1] if len(antes_da_fala) else f - 1
    return Pausa(float((k0 + fim_da_fala) * medida.passo_s),
                 float((k0 + comeco_da_fala) * medida.passo_s) + JANELA_S)


def _escolher(quieto: np.ndarray, fala: np.ndarray, a: int, b: int, minimo: int
              ) -> tuple[int, int] | None:
    """A pausa que mais cobre as janelas de ``a`` a ``b``, inteira, mesmo passando delas; os
    pedaços quietos se emendam por cima do que não é fala (um respiro)."""
    pausas: list[tuple[int, int]] = []
    for c, f in _corridas(quieto):
        if pausas and not fala[pausas[-1][1]:c].any():
            pausas[-1] = (pausas[-1][0], f)
        else:
            pausas.append((c, f))
    candidatas = [(min(f, b) - max(c, a), c, f) for c, f in pausas
                  if f - c >= minimo and min(f, b) > max(c, a)]
    if not candidatas:
        return None
    _, c, f = max(candidatas)
    return c, f


def _calmas(faixas: list[np.ndarray], de: int, ate: int, fala: slice) -> np.ndarray:
    """As janelas entre ``de`` e ``ate`` em que todas as faixas estão perto do fundo dali, que
    nunca fica mais que :data:`ABAIXO_DA_PALAVRA_DB` abaixo da ``fala`` ao lado."""
    calmas = []
    for db in faixas:
        fundo = float(np.percentile(db[de:ate], 10))
        if len(db[fala]):
            fundo = max(fundo, float(db[fala].max()) - ABAIXO_DA_PALAVRA_DB)
        calmas.append(_quieta(db[de:ate], fundo, BORDA_DB))
    return de + np.flatnonzero(np.all(calmas, axis=0))


def entre(medida: Atividade, anterior: Palavra | None, seguinte: Palavra | None,
          duracao: float | None = None) -> Pausa | None:
    """A pausa entre duas palavras do Whisper. Sem a anterior, a que vem antes da fala; sem a
    seguinte, a que vem depois dela."""
    if anterior is None and seguinte is None:
        return None
    de = anterior.fim - ANTES_S if anterior else seguinte.inicio - MARGEM_S
    ate = seguinte.inicio + DEPOIS_S if seguinte else anterior.fim + MARGEM_S
    if duracao is not None:
        ate = min(ate, duracao)
    return pausa(medida, de, ate)


def comeco(medida: Atividade, palavra: Palavra, anterior: Palavra | None = None) -> float:
    """Onde o som de ``palavra`` começa, depois da pausa que vem antes dela (sem pausa, o
    tempo do Whisper)."""
    achada = entre(medida, anterior, palavra)
    return achada.comeco_da_fala if achada else palavra.inicio


def fim(medida: Atividade, palavra: Palavra, seguinte: Palavra | None = None,
        duracao: float | None = None) -> float:
    """Onde o som de ``palavra`` acaba, antes da pausa que vem depois dela (sem pausa, o
    tempo do Whisper)."""
    achada = entre(medida, palavra, seguinte, duracao)
    return achada.fim_da_fala if achada else palavra.fim


__all__ = ["Atividade", "Pausa", "atividade", "comeco", "entre", "fim", "pausa"]
