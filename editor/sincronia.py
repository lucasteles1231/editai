"""
O áudio gravado à parte: a câmera gravou um som ruim e o microfone (ou o celular) gravou à
parte. O Editai acha, pelo próprio som, quanto um está atrasado em relação ao outro, e o vídeo
passa a ser lido no tempo certo da fala.

**Como:**

1. **O atraso grosso.** Os dois sons viram o "fluxo espectral" (quanto o espectro sobe de um
   quadro de 10 ms para o seguinte): os ataques das sílabas, iguais nos dois microfones, e quase
   cegos ao volume, ao eco e ao chiado de cada um. Os dois fluxos são correlacionados por FFT,
   no arquivo inteiro: o pico é o atraso, com 10 ms de precisão.
2. **O fino.** Em cada janela de 8 s, primeiro o grosso de novo, só ali (em ±200 ms do geral:
   com a deriva, o atraso do começo e o do fim podem estar mais longe que a busca fina). Depois,
   em ±30 ms dele, o GCC-PHAT (a correlação pela fase,
   que quase não liga para a cor de cada microfone) no som a 16 kHz dá o atraso na amostra. Só
   na banda da voz (de 80 Hz a 4 kHz), e com a fase pesada pela força do sinal (o PHAT-β, com
   β = 0,75): o PHAT puro dá o mesmo peso às frequências de cima, onde só há o chiado de cada
   microfone, e pegava o pico de um período do tom ao lado (de 4,5 a 10 ms).
3. **A confiança.** O pico contra o segundo maior, longe dele. Com sons que não são da mesma
   gravação, os dois ficam parecidos, e :attr:`Alinhamento.ok` é falso: o Editai pede ajuda
   (uma palma no começo) e deixa ajustar à mão.
4. **A deriva.** Dois aparelhos não contam o tempo igual: uns 50 ppm separam 30 ms numa
   gravação de 10 min. O fino é medido no começo, no meio e no fim, e a reta deles dá a deriva,
   que só vale se passar de 1 quadro no arquivo inteiro e se as três medidas concordarem.

**O tempo:** um evento em ``t`` no som à parte acontece em ``Alinhamento.no_video(t)`` no
vídeo. Um clipe curto da câmera também acha o seu lugar num áudio longo.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

#: A taxa em que os sons são comparados.
TAXA = 16_000
#: O passo do fluxo espectral (10 ms) e o tamanho da janela dele.
PASSO = 160
JANELA = 512
#: A janela do atraso fino, e o quanto ele procura em volta do grosso (pelo fluxo a cada 1 ms)
#: e depois em volta dele (pelo GCC-PHAT).
JANELA_FINA_S = 8.0
BUSCA_FINA_S = 0.03
#: O grosso de cada janela procura até aqui em volta do grosso geral.
BUSCA_LOCAL_S = 0.2
#: A banda da voz e o peso da fase no GCC-PHAT (β = 1 é o PHAT puro; 0, a correlação comum).
BANDA_HZ = (80.0, 4000.0)
BETA = 0.75
#: O pico precisa passar o segundo maior (longe dele) por esta razão.
CONFIANCA_MINIMA = 1.6
#: O que conta como "longe do pico", para achar o segundo maior.
LONGE_S = 0.25
#: A deriva só entra se separar mais que um quadro no arquivo inteiro, e se as medidas
#: concordarem com a reta dela até este tanto.
UM_QUADRO_S = 1 / 30
CONCORDAM_S = 0.002


@dataclass(frozen=True)
class Alinhamento:
    #: Um evento em ``t`` no som à parte acontece em ``atraso_s + t * (1 + deriva)`` no vídeo.
    atraso_s: float
    deriva: float = 0.0
    #: O pico contra o segundo maior: abaixo de :data:`CONFIANCA_MINIMA`, não confie.
    confianca: float = 0.0
    #: As medidas finas: (o tempo no som à parte, o atraso ali).
    medidas: tuple[tuple[float, float], ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return self.confianca >= CONFIANCA_MINIMA

    @property
    def deriva_ppm(self) -> float:
        return self.deriva * 1e6

    def no_video(self, t: float) -> float:
        return self.atraso_s + t * (1.0 + self.deriva)

    def para_dict(self) -> dict:
        # o ajustado à mão não tem medida: a confiança vai vazia (o JSON não tem infinito)
        confianca = round(self.confianca, 2) if np.isfinite(self.confianca) else None
        return {"atraso_s": round(self.atraso_s, 5), "deriva_ppm": round(self.deriva_ppm, 2),
                "confianca": confianca, "ok": self.ok,
                "medidas": [[round(t, 3), round(a, 5)] for t, a in self.medidas]}


class SemSincronia(Exception):
    """Os sons são curtos demais, ou mudos."""


def fluxo(x: np.ndarray, passo: int = PASSO, janela: int = JANELA) -> np.ndarray:
    """O fluxo espectral, um valor a cada ``passo`` amostras (10 ms), com média zero e desvio
    um."""
    x = np.asarray(x, dtype=np.float32)
    if len(x) < janela:
        return np.zeros(0, dtype=np.float32)
    quadros = np.lib.stride_tricks.sliding_window_view(x, janela)[::passo]
    espectro = np.abs(np.fft.rfft(quadros * np.hanning(janela).astype(np.float32), axis=1))
    log = np.log1p(1000.0 * espectro)
    subida = np.maximum(np.diff(log, axis=0, prepend=log[:1]), 0.0).sum(axis=1)
    subida = subida - subida.mean()
    desvio = subida.std()
    return (subida / desvio).astype(np.float32) if desvio > 0 else subida.astype(np.float32)


def _correlacao(a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """A correlação cruzada de ``a`` e ``b`` em todos os atrasos: ``valores[k]`` é a soma de
    ``a[n + atrasos[k]] * b[n]``."""
    n = len(a) + len(b) - 1
    tamanho = 1 << (n - 1).bit_length()
    c = np.fft.irfft(np.fft.rfft(a, tamanho) * np.conj(np.fft.rfft(b, tamanho)), tamanho)
    atrasos = np.concatenate([np.arange(0, len(a)), np.arange(-(len(b) - 1), 0)])
    valores = np.concatenate([c[:len(a)], c[tamanho - (len(b) - 1):]])
    return atrasos, valores


def atraso_grosso(camera: np.ndarray, separado: np.ndarray) -> tuple[float, float]:
    """O atraso (com 10 ms de precisão) e a confiança, pelo fluxo espectral."""
    return _grosso(fluxo(camera), fluxo(separado))


def _grosso(fc: np.ndarray, fs: np.ndarray) -> tuple[float, float]:
    if len(fc) < 10 or len(fs) < 10:
        raise SemSincronia("os sons são curtos demais para sincronizar")
    atrasos, valores = _correlacao(fc, fs)
    # o atraso conta pela sobreposição: um pico com 2 s em comum não vale um com 2 min
    comum = np.minimum(len(fc), np.minimum(len(fs), np.minimum(len(fs) + atrasos,
                                                                len(fc) - atrasos)))
    valores = np.where(comum > 0, valores / np.sqrt(np.maximum(comum, 1)), 0.0)
    pico = int(np.argmax(valores))
    longe = np.abs(atrasos - atrasos[pico]) > LONGE_S * TAXA / PASSO
    segundo = valores[longe].max() if longe.any() else 0.0
    confianca = float(valores[pico] / segundo) if segundo > 0 else float("inf")
    return float(atrasos[pico] * PASSO / TAXA), confianca


def _gcc_phat(a: np.ndarray, b: np.ndarray, busca: int) -> float:
    """Quanto ``a`` está atrasado em relação a ``b``, em amostras (com fração), procurando até
    ``busca`` amostras para cada lado."""
    n = len(a) + len(b)
    tamanho = 1 << (n - 1).bit_length()
    cruzado = np.fft.rfft(a, tamanho) * np.conj(np.fft.rfft(b, tamanho))
    cruzado /= np.maximum(np.abs(cruzado), 1e-12) ** BETA
    hz = np.fft.rfftfreq(tamanho, 1 / TAXA)
    cruzado[(hz < BANDA_HZ[0]) | (hz > BANDA_HZ[1])] = 0
    c = np.fft.irfft(cruzado, tamanho)
    c = np.concatenate([c[-busca:], c[:busca + 1]])
    k = int(np.argmax(c))
    fracao = 0.0
    if 0 < k < len(c) - 1:                 # a parábola nos três pontos do pico
        y0, y1, y2 = c[k - 1], c[k], c[k + 1]
        denominador = y0 - 2 * y1 + y2
        if denominador != 0:
            fracao = 0.5 * (y0 - y2) / denominador
    return k - busca + fracao


def _grosso_local(fc: np.ndarray, fs: np.ndarray, atraso_s: float, centro_s: float) -> float:
    """O grosso só numa janela em volta de ``centro_s`` (no som à parte), em ±200 ms do geral."""
    por_s = TAXA / PASSO
    meio = int(JANELA_FINA_S / 2 * por_s)
    i0, i1 = max(0, int(centro_s * por_s) - meio), int(centro_s * por_s) + meio
    geral, busca = round(atraso_s * por_s), int(BUSCA_LOCAL_S * por_s)
    melhor, melhor_valor = geral, -np.inf
    for k in range(geral - busca, geral + busca + 1):
        a0, a1 = max(i0, -k, 0), min(i1, len(fs), len(fc) - k)
        if a1 - a0 < meio:
            continue
        valor = float(np.dot(fc[a0 + k:a1 + k], fs[a0:a1])) / (a1 - a0)
        if valor > melhor_valor:
            melhor, melhor_valor = k, valor
    return melhor / por_s


def _fino(camera: np.ndarray, separado: np.ndarray, atraso_s: float, centro_s: float
          ) -> float | None:
    """O atraso na amostra, numa janela em volta de ``centro_s`` (no som à parte)."""
    janela = int(JANELA_FINA_S * TAXA)
    inicio_s = max(0, int(centro_s * TAXA) - janela // 2)
    deslocado = round(atraso_s * TAXA)
    inicio_c = inicio_s + deslocado
    if inicio_c < 0:
        inicio_s -= inicio_c
        inicio_c = 0
    fim = min(len(separado) - inicio_s, len(camera) - inicio_c, janela)
    if fim < TAXA:                         # menos de 1 s em comum: não dá para medir aqui
        return None
    s = separado[inicio_s:inicio_s + fim].astype(np.float64)
    c = camera[inicio_c:inicio_c + fim].astype(np.float64)
    if not s.any() or not c.any():
        return None
    resto = _gcc_phat(c, s, int(BUSCA_FINA_S * TAXA))
    return (deslocado + resto) / TAXA


def medir(camera: np.ndarray, separado: np.ndarray) -> Alinhamento:
    """O alinhamento entre o som da câmera e o gravado à parte (mono, a 16 kHz)."""
    camera = np.asarray(camera, dtype=np.float32)
    separado = np.asarray(separado, dtype=np.float32)
    fc, fs = fluxo(camera), fluxo(separado)
    grosso, confianca = _grosso(fc, fs)
    # o trecho do som à parte que a câmera também ouviu
    comeco = max(0.0, -grosso)
    fim = min(len(separado) / TAXA, len(camera) / TAXA - grosso)
    if fim - comeco < 1.0:
        raise SemSincronia("os dois sons têm menos de 1 s em comum")
    meio = JANELA_FINA_S / 2
    centros = sorted({max(comeco + meio, min(fim - meio, c))
                      for c in (comeco + meio, (comeco + fim) / 2, fim - meio)})
    medidas = []
    for c in centros:
        local = _grosso_local(fc, fs, grosso, c)
        a = _fino(camera, separado, local, c)
        if a is not None and abs(a - local) <= BUSCA_FINA_S:
            medidas.append((c, a))
    if not medidas:
        return Alinhamento(grosso, 0.0, confianca, ())
    tempos = np.array([t for t, _ in medidas])
    atrasos = np.array([a for _, a in medidas])
    atraso, deriva = float(np.median(atrasos)), 0.0
    if len(medidas) >= 3 and tempos[-1] - tempos[0] > 0:
        b, a0 = np.polyfit(tempos, atrasos, 1)
        concordam = np.abs(atrasos - (a0 + b * tempos)).max() <= CONCORDAM_S
        if concordam and abs(b) * (fim - comeco) > UM_QUADRO_S:
            atraso, deriva = float(a0), float(b)
    return Alinhamento(atraso, deriva, confianca, tuple(medidas))


def de_arquivos(camera: Path, separado: Path) -> Alinhamento:
    """O alinhamento entre o som de um vídeo (ou áudio) da câmera e o gravado à parte."""
    from editor import video as video_mod

    a = video_mod.ler_audio_mono(Path(camera), TAXA)
    b = video_mod.ler_audio_mono(Path(separado), TAXA)
    if not a.size or not b.size:
        raise SemSincronia("um dos arquivos não tem som")
    return medir(a, b)


__all__ = ["CONFIANCA_MINIMA", "TAXA", "Alinhamento", "SemSincronia", "atraso_grosso",
           "de_arquivos", "fluxo", "medir"]
