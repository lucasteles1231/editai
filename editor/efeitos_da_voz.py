"""
Os efeitos na voz: robô, esquilo, cantado, rádio, fantasma… e os seus.

Um efeito é um texto curto, ``tom=9,coral=20,agudos=3``: cabe nas opções de edição, viaja
nos presets, entra na chave do cache e se digita na linha de comando. Cada controle tem
uma faixa (semitons, % ou dB) e o que fica de fora vale zero.

Os efeitos entram em duas etapas, e as duas devolvem **o mesmo número de amostras** (a
legenda, os cortes e o bipe dependem disso):

- :func:`aplicar_na_voz` (mono, antes do tratamento): o tom, a afinação, o robô, o
  sussurro, o rádio, a distorção e o equalizador;
- :func:`aplicar_no_ambiente` (estéreo, depois do tratamento e do bipe): o vibrato, o
  coral, o eco e a sala. O bipe vem antes para a sílaba proibida não voltar na cauda do
  eco, e o tratamento antes para o expansor do estúdio não cortar a cauda da sala.

O tom é o do FFmpeg (``asetrate`` + ``atempo``): a duração fica igual e o timbre acompanha
o tom, que é o que faz o esquilo e o monstro. A afinação (o "cantado") é feita aqui: a F0
pelo YIN, puxada para o semitom mais perto, e o TD-PSOLA muda o tom sem mudar o timbre.
O robô e o sussurro trocam a fase da STFT (zerada, com passo fixo, e aleatória); a sala é
uma resposta sintética, convolvida em blocos. Nada a instalar.
"""
from __future__ import annotations

import json
import logging
import re
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from editor import voz

logger = logging.getLogger(__name__)

TAXA = voz.TAXA


@dataclass(frozen=True)
class Controle:
    chave: str
    titulo: str
    #: "tom", "carater", "ambiente" ou "equalizador" (os grupos da página).
    grupo: str
    minimo: int
    maximo: int
    #: "semitons", "%" ou "dB".
    unidade: str


CONTROLES = (
    Controle("tom", "Tom", "tom", -12, 12, "semitons"),
    Controle("afinacao", "Cantado (afinação)", "tom", 0, 100, "%"),
    Controle("robo", "Robô", "carater", 0, 100, "%"),
    Controle("sussurro", "Sussurro", "carater", 0, 100, "%"),
    Controle("radio", "Rádio", "carater", 0, 100, "%"),
    Controle("distorcao", "Distorção", "carater", 0, 100, "%"),
    Controle("vibrato", "Vibrato", "ambiente", 0, 100, "%"),
    Controle("coral", "Coral", "ambiente", 0, 100, "%"),
    Controle("eco", "Eco", "ambiente", 0, 100, "%"),
    Controle("sala", "Sala", "ambiente", 0, 100, "%"),
    Controle("graves", "Graves", "equalizador", -12, 12, "dB"),
    Controle("medios", "Médios", "equalizador", -12, 12, "dB"),
    Controle("agudos", "Agudos", "equalizador", -12, 12, "dB"),
)
_POR_CHAVE = {c.chave: c for c in CONTROLES}
#: Os controles que mexem no estéreo, depois do tratamento.
AMBIENTE = ("vibrato", "coral", "eco", "sala")

#: O zumbido do robô: a STFT é refeita com a fase zerada a cada 1/120 s.
ROBO_HZ = 120
#: O fim cortado do eco e da sala some em 50 ms, sem estalo.
FADE_S = 0.05
#: O "ouvir antes" (e a amostra do estúdio): 8 s, de 3 a 20.
PREVIA_S = 8.0
PREVIA_MINIMA_S, PREVIA_MAXIMA_S = 3.0, 20.0


class EfeitoInvalido(ValueError):
    """O efeito não serve (a mensagem diz por quê)."""


# ── o texto do efeito ───────────────────────────────────────────────────


def _faixa(c: Controle) -> str:
    sinal = "+" if c.minimo < 0 else ""
    return f"{c.minimo} a {sinal}{c.maximo} {c.unidade}".replace("-", "−")


def ler(texto: str | None) -> dict[str, int]:
    """``"tom=9, coral=20"`` vira ``{"tom": 9, "coral": 20}``. Vazio é nenhum efeito; os
    zeros saem. Uma chave desconhecida ou um valor fora da faixa dá :class:`EfeitoInvalido`."""
    efeito: dict[str, int] = {}
    for parte in re.split(r"[,;\s]+", str(texto or "").strip()):
        if not parte:
            continue
        chave, igual, valor = parte.partition("=")
        chave = chave.strip().lower()
        if chave not in _POR_CHAVE:
            raise EfeitoInvalido(f"efeito desconhecido: {chave or parte} (use "
                                 f"{', '.join(_POR_CHAVE)})")
        c = _POR_CHAVE[chave]
        if not igual or not re.fullmatch(r"[+-]?\d{1,3}", valor.strip()):
            raise EfeitoInvalido(f"o valor de {c.titulo.lower()} é um número inteiro: "
                                 f"{chave}=10")
        n = int(valor)
        if not c.minimo <= n <= c.maximo:
            raise EfeitoInvalido(f"{c.titulo} vai de {_faixa(c)}")
        if n:
            efeito[chave] = n
    return efeito


def escrever(efeito: dict[str, int]) -> str:
    """O caminho de volta, na ordem dos controles: o mesmo efeito dá sempre o mesmo texto."""
    return ",".join(f"{c.chave}={efeito[c.chave]}" for c in CONTROLES if efeito.get(c.chave))


def normalizar(texto: str | None) -> str:
    return escrever(ler(texto))


# ── o tom, a afinação e o PSOLA ─────────────────────────────────────────


def _tom(x: np.ndarray, semitons: float) -> np.ndarray:
    k = 2 ** (semitons / 12)
    return voz.filtrar(x, f"asetrate={round(TAXA * k)},aresample={TAXA},atempo={1 / k:.6f}")


_F0_TAXA = 16_000
_F0_PASSO = 160            # 10 ms
_F0_JANELA = 512
_F0_MIN, _F0_MAX = 70.0, 500.0
_YIN_LIMIAR = 0.2


def _f0(x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """A F0 (Hz) de 10 em 10 ms pelo YIN, a 16 kHz, e se cada quadro tem voz. O quadro i
    fica centrado em ``i * 10 ms + 16 ms``."""
    baixa = voz.filtrar(x, "lowpass=f=7000,lowpass=f=7000")[:: TAXA // _F0_TAXA]
    tau_max, tau_min = int(_F0_TAXA / _F0_MIN), int(_F0_TAXA / _F0_MAX)
    n = _F0_JANELA + tau_max
    total = max(0, (len(baixa) - n) // _F0_PASSO + 1)
    f0 = np.zeros(total)
    vozeado = np.zeros(total, bool)
    if not total:
        return f0, vozeado
    nfft = 1 << int(np.ceil(np.log2(n + _F0_JANELA)))
    todos = np.lib.stride_tricks.sliding_window_view(baixa.astype(np.float64), n)[::_F0_PASSO]
    piso = 10 ** (-50 / 20)
    taus = np.arange(1, tau_max + 1)
    for ini in range(0, total, 2000):
        q = todos[ini:ini + 2000]
        a = np.fft.rfft(q[:, :_F0_JANELA], nfft)
        r = np.fft.irfft(np.conj(a) * np.fft.rfft(q, nfft), nfft)[:, : tau_max + 1]
        acumulado = np.concatenate([np.zeros((len(q), 1)), np.cumsum(q ** 2, axis=1)], axis=1)
        e0 = acumulado[:, _F0_JANELA]
        e_tau = acumulado[:, _F0_JANELA: _F0_JANELA + tau_max + 1] - acumulado[:, : tau_max + 1]
        d = np.maximum(e0[:, None] + e_tau - 2 * r, 0.0)[:, 1:]
        cmnd = d * taus / np.maximum(np.cumsum(d, axis=1), 1e-12)
        rms = np.sqrt(e0 / _F0_JANELA)
        for k in range(len(q)):
            if rms[k] < piso:
                continue
            c = cmnd[k]
            abaixo = np.flatnonzero(c[tau_min - 1:] < _YIN_LIMIAR)
            if not len(abaixo):
                continue
            t = abaixo[0] + tau_min - 1
            while t + 1 < len(c) and c[t + 1] < c[t]:
                t += 1
            if 0 < t < len(c) - 1:                      # a parábola em volta do mínimo
                den = c[t - 1] - 2 * c[t] + c[t + 1]
                fino = t + (0.5 * (c[t - 1] - c[t + 1]) / den if den > 1e-12 else 0.0)
            else:
                fino = float(t)
            f0[ini + k] = _F0_TAXA / (fino + 1)
            vozeado[ini + k] = True
    # a mediana de 5 quadros tira os saltos de oitava isolados
    if total >= 5:
        com_nan = np.where(vozeado, f0, np.nan)
        janelas = np.lib.stride_tricks.sliding_window_view(np.pad(com_nan, 2, mode="edge"), 5)
        with warnings.catch_warnings():              # janela toda sem voz: NaN, e tudo bem
            warnings.simplefilter("ignore", RuntimeWarning)
            mediana = np.nanmedian(janelas, axis=1)
        f0 = np.where(vozeado, mediana, 0.0)
    return f0, vozeado


def _desvio_da_afinacao(f0: np.ndarray, vozeado: np.ndarray, forca: float) -> np.ndarray:
    """Quantos semitons cada quadro com voz anda até a nota: a nota mais perto, mantida
    enquanto a voz não se afasta mais de 0,75 semitom dela (sem pular entre duas notas)."""
    desvio = np.zeros(len(f0))
    nota = None
    for i in range(len(f0)):
        if not vozeado[i] or f0[i] <= 0:
            nota = None
            continue
        midi = 69 + 12 * np.log2(f0[i] / 440.0)
        if nota is None or abs(midi - nota) > 0.75:
            nota = round(midi)
        desvio[i] = (nota - midi) * forca
    return desvio


def _psola(x: np.ndarray, f0: np.ndarray, vozeado: np.ndarray, desvio: np.ndarray
           ) -> np.ndarray:
    """O TD-PSOLA: grãos de dois períodos, cortados nas marcas de pitch da voz e
    recolocados com o período novo. O timbre (os formantes) fica; a duração também."""
    n = len(x)
    centro = (np.arange(len(f0)) * _F0_PASSO + _F0_JANELA / 2) / _F0_TAXA * TAXA

    def quadro(t: float) -> int:
        return int(np.clip(np.searchsorted(centro, t), 0, len(f0) - 1))

    surdo = int(0.005 * TAXA)                     # sem voz: grãos de 5 ms, sem mudança
    marcas, periodos, razoes = [], [], []
    p, antes_vozeado = 0, False
    while p < n:
        i = quadro(p)
        if vozeado[i] and f0[i] > 0:
            periodo = TAXA / f0[i]
            if antes_vozeado:
                ini, fim = int(p - 0.25 * periodo), int(p + 0.25 * periodo) + 1
            else:
                ini, fim = int(p), int(p + periodo) + 1
            trecho = x[max(0, ini):min(n, fim)]
            p = max(0, ini) + int(np.argmax(trecho)) if len(trecho) else p
            marcas.append(p)
            periodos.append(round(periodo))
            razoes.append(2 ** (desvio[i] / 12))
            p = int(p + periodo)
            antes_vozeado = True
        else:
            marcas.append(p)
            periodos.append(surdo)
            razoes.append(1.0)
            p += surdo
            antes_vozeado = False
    marcas_a = np.asarray(marcas)
    y = np.zeros(n, np.float64)
    peso = np.zeros(n, np.float64)
    janelas: dict[int, np.ndarray] = {}
    t = float(marcas_a[0]) if len(marcas_a) else 0.0
    while t < n:
        k = int(np.clip(np.searchsorted(marcas_a, t), 0, len(marcas_a) - 1))
        if k and abs(marcas_a[k - 1] - t) < abs(marcas_a[k] - t):
            k -= 1
        a, periodo, r = int(marcas_a[k]), periodos[k], razoes[k]
        w = janelas.get(periodo)
        if w is None:
            w = janelas[periodo] = np.hanning(2 * periodo + 1)
        c = round(t)
        # o pedaço do grão que cabe dentro do áudio, na origem (a) e no destino (c)
        de_ini = max(0, periodo - a, periodo - c)
        de_fim = min(2 * periodo + 1, n - a + periodo, n - c + periodo)
        if de_fim > de_ini:
            grao = x[a - periodo + de_ini: a - periodo + de_fim] * w[de_ini:de_fim]
            y[c - periodo + de_ini: c - periodo + de_fim] += grao
            peso[c - periodo + de_ini: c - periodo + de_fim] += w[de_ini:de_fim]
        t += max(1.0, periodo / r)
    return np.where(peso > 1e-3, y / np.maximum(peso, 1e-3), 0.0).astype(np.float32)


def _afinar(x: np.ndarray, forca: float) -> np.ndarray:
    f0, vozeado = _f0(x)
    if not vozeado.any():
        return x
    return _psola(x, f0, vozeado, _desvio_da_afinacao(f0, vozeado, forca))


# ── o robô, o sussurro, o rádio e a distorção ───────────────────────────


def _rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.asarray(x, np.float64) ** 2)) + 1e-12)


def _misturar(seco: np.ndarray, molhado: np.ndarray, quanto: float) -> np.ndarray:
    """O molhado no volume do seco, misturado na proporção pedida."""
    molhado = molhado * (_rms(seco) / _rms(molhado))
    return ((1 - quanto) * seco + quanto * molhado).astype(np.float32)


def _robo(x: np.ndarray) -> np.ndarray:
    n, passo = 1024, round(TAXA / ROBO_HZ)
    espectro, janela = voz._stft(x, n, passo)
    # a fase zerada (com o pulso no meio do quadro) a cada passo: um zumbido no tom do passo
    centrado = np.abs(espectro) * np.where(np.arange(espectro.shape[1]) % 2, -1.0, 1.0)
    return voz._istft(centrado, janela, n, passo, len(x))


def _sussurro(x: np.ndarray) -> np.ndarray:
    """Ruído com o formato das vogais: o envelope de cada quadro (o cepstro abaixo de
    1,5 ms, que guarda os formantes e deixa os harmônicos de fora) vezes um ruído
    gaussiano, sem os graves e com mais agudo. A primeira versão (a fase aleatória sobre o
    espectro inteiro) punha o ruído nos graves e soava como vento; esta foi a escolhida
    de ouvido pelo dono, entre três (11/10)."""
    n, passo = 1024, 256
    espectro, janela = voz._stft(x, n, passo)
    cepstro = np.fft.irfft(np.log(np.abs(espectro) + 1e-7), n=n, axis=1)
    corte = int(0.0015 * TAXA)
    cepstro[:, corte:n - corte] = 0
    envelope = np.exp(np.fft.rfft(cepstro, n=n, axis=1).real)
    rng = np.random.default_rng(7)
    ruido = (rng.standard_normal(espectro.shape)
             + 1j * rng.standard_normal(espectro.shape)) / np.sqrt(2)
    ar = voz._istft(envelope * ruido, janela, n, passo, len(x))
    return voz.filtrar(ar, "highpass=f=650,highpass=f=650,treble=g=8:f=2500")


def _radio(x: np.ndarray, quanto: float) -> np.ndarray:
    baixo, alto = 100 + 400 * quanto, 8000 - 5200 * quanto
    return voz.filtrar(x, f"highpass=f={baixo:.0f},highpass=f={baixo:.0f},"
                          f"lowpass=f={alto:.0f},lowpass=f={alto:.0f},"
                          f"equalizer=f=1500:t=q:w=1:g={6 * quanto:.1f}")


def _distorcao(x: np.ndarray, quanto: float) -> np.ndarray:
    pico = float(np.percentile(np.abs(x), 99.5)) or 1.0
    return np.tanh((1 + 19 * quanto) * x / pico).astype(np.float32)


def _equalizar(x: np.ndarray, graves: int, medios: int, agudos: int) -> np.ndarray:
    filtros = []
    if graves:
        filtros.append(f"bass=g={graves}:f=150:w=0.7")
    if medios:
        filtros.append(f"equalizer=f=1000:t=q:w=1:g={medios}")
    if agudos:
        filtros.append(f"treble=g={agudos}:f=4000:w=0.7")
    return voz.filtrar(x, ",".join(filtros)) if filtros else x


def _mesmo_volume(y: np.ndarray, referencia: np.ndarray) -> np.ndarray:
    alvo = voz.lufs(referencia)
    return voz.limitar(voz.nivelar(y, alvo) if alvo > -69.9 else y)


def aplicar_na_voz(x: np.ndarray, efeito: dict[str, int]) -> np.ndarray:
    """A voz mono (``TAXA``) com o tom, a afinação, o caráter e o equalizador, no volume
    em que chegou e com o mesmo número de amostras."""
    x = np.ascontiguousarray(x, dtype=np.float32)
    if not len(x) or not any(efeito.get(k) for k in _POR_CHAVE if k not in AMBIENTE):
        return x
    y = x
    if efeito.get("afinacao"):
        y = _afinar(y, efeito["afinacao"] / 100)
    if efeito.get("tom"):
        y = _tom(y, efeito["tom"])
    if efeito.get("robo"):
        y = _misturar(y, _robo(y), efeito["robo"] / 100)
    if efeito.get("sussurro"):
        y = _misturar(y, _sussurro(y), efeito["sussurro"] / 100)
    if efeito.get("radio"):
        y = _radio(y, efeito["radio"] / 100)
    if efeito.get("distorcao"):
        y = _distorcao(y, efeito["distorcao"] / 100)
    y = _equalizar(y, efeito.get("graves", 0), efeito.get("medios", 0), efeito.get("agudos", 0))
    return _mesmo_volume(np.ascontiguousarray(y[: len(x)], np.float32), x)


# ── o ambiente ──────────────────────────────────────────────────────────

#: O coral: três vozes atrasadas e moduladas, diferentes em cada lado.
_CORAL = ("chorus=0.6:0.9:50|60|40:0.4|0.32|0.3:0.25|0.4|0.3:2|2.3|1.3",
          "chorus=0.6:0.9:45|65|35:0.4|0.3|0.32:0.3|0.35|0.27:2.2|1.9|1.5")


def _vibrato(x: np.ndarray, profundidade: float) -> np.ndarray:
    """O ``vibrato`` do FFmpeg não zera o buffer de atraso (5 ms, alocado com
    ``av_malloc``): as primeiras amostras saem do lixo da memória, que no Linux veio NaN
    (no Mac, zero por sorte). Um silêncio de 20 ms na frente recebe o lixo e sai depois."""
    folga = int(0.02 * TAXA)
    y = voz.filtrar(np.concatenate([np.zeros(folga, np.float32), x]),
                    f"vibrato=f=5.5:d={profundidade:.3f}")
    return y[folga:]


def _resposta_da_sala(quanto: float, semente: int) -> np.ndarray:
    """Ruído com decaimento exponencial (RT60 de 0,3 a 2,5 s) e um pré-atraso de 15 ms."""
    rt60 = 0.3 + 2.2 * quanto
    t = np.arange(int(rt60 * TAXA)) / TAXA
    rng = np.random.default_rng(semente)
    cauda = rng.standard_normal(len(t)) * np.exp(-6.9 * t / rt60)
    # o ar e as paredes comem o agudo da cauda: uma média móvel que cresce com o tempo
    cauda = np.convolve(cauda, np.ones(3) / 3, mode="same")
    resposta = np.concatenate([np.zeros(int(0.015 * TAXA)), cauda])
    return (resposta / np.sqrt(np.sum(resposta ** 2))).astype(np.float32)


def _convolver(x: np.ndarray, h: np.ndarray) -> np.ndarray:
    """A convolução em blocos (sobrepõe e soma), cortada no comprimento de ``x``."""
    bloco = 1 << 16
    nfft = 1 << int(np.ceil(np.log2(bloco + len(h) - 1)))
    resposta = np.fft.rfft(h, nfft)
    y = np.zeros(len(x) + nfft, np.float64)
    for i in range(0, len(x), bloco):
        parte = np.fft.irfft(np.fft.rfft(x[i:i + bloco], nfft) * resposta, nfft)
        y[i:i + nfft] += parte
    return y[: len(x)].astype(np.float32)


def aplicar_no_ambiente(estereo: np.ndarray, efeito: dict[str, int]) -> np.ndarray:
    """A voz em estéreo (amostras × 2) com o vibrato, o coral, o eco e a sala, no mesmo
    volume e no mesmo comprimento (o fim cortado some em 50 ms)."""
    estereo = np.ascontiguousarray(estereo, dtype=np.float32)
    if not len(estereo) or not any(efeito.get(k) for k in AMBIENTE):
        return estereo
    lados = [estereo[:, 0].copy(), estereo[:, 1].copy()]
    if efeito.get("vibrato"):
        lados = [_vibrato(lado, 0.1 + 0.6 * efeito["vibrato"] / 100) for lado in lados]
    if efeito.get("coral"):
        c = efeito["coral"] / 100
        coros = [voz.filtrar(lado, cadeia) for lado, cadeia in zip(lados, _CORAL, strict=True)]
        lados = [lado + c * coro * (_rms(lado) / _rms(coro))
                 for lado, coro in zip(lados, coros, strict=True)]
    if efeito.get("eco"):
        e = efeito["eco"] / 100
        lados = [voz.filtrar(lado, f"aecho=1:1:{atraso}|{2 * atraso}:{0.5 * e:.3f}|"
                                   f"{0.28 * e:.3f}")
                 for lado, atraso in zip(lados, (240, 270), strict=True)]
    if efeito.get("sala"):
        s = efeito["sala"] / 100
        lados = [(1 - 0.25 * s) * lado + 0.9 * s * molhado * (_rms(lado) / _rms(molhado))
                 for lado, molhado in ((lado, _convolver(lado, _resposta_da_sala(s, 11 + k)))
                                       for k, lado in enumerate(lados))]
    y = np.stack(lados, axis=1).astype(np.float32)
    fade = min(len(y), int(FADE_S * TAXA))
    if fade:
        y[-fade:] *= np.linspace(1, 0, fade, dtype=np.float32)[:, None]
    return _mesmo_volume(y, estereo)


def aplicar(x: np.ndarray, efeito: dict[str, int]) -> np.ndarray:
    """As duas etapas numa voz mono: o estéreo pronto (o "ouvir antes")."""
    mono = aplicar_na_voz(x, efeito)
    return aplicar_no_ambiente(np.stack([mono, mono], axis=1), efeito)


def previa(x: np.ndarray, efeito: dict[str, int], tratamento: str = "original",
           segundos: float = PREVIA_S) -> np.ndarray:
    """O "ouvir antes": os primeiros segundos com voz pelo mesmo caminho da edição (o
    efeito na voz, o tratamento, o ambiente), no volume final. Estéreo."""
    trecho = trecho_para_ouvir(x, segundos)
    if not len(trecho):
        return np.zeros((0, 2), np.float32)
    junto, _ = voz.juntar([trecho], tratamento)
    estereo = voz.tratar(aplicar_na_voz(junto, efeito), tratamento)
    estereo = aplicar_no_ambiente(estereo, efeito)
    return voz.limitar(voz.nivelar(estereo, voz.FINAL_LUFS))


def trecho_para_ouvir(x: np.ndarray, segundos: float = PREVIA_S) -> np.ndarray:
    """Os primeiros ``segundos`` com voz: do primeiro trecho de 50 ms acima de −40 dBFS
    (com 0,2 s antes), ou do começo."""
    passo = int(0.05 * TAXA)
    env = voz._envelope(x, passo)
    com_voz = np.flatnonzero(20 * np.log10(env + 1e-10) > -40)
    ini = max(0, int(com_voz[0]) * passo - int(0.2 * TAXA)) if len(com_voz) else 0
    return np.ascontiguousarray(x[ini: ini + int(segundos * TAXA)], np.float32)


# ── os prontos e os seus ────────────────────────────────────────────────


@dataclass(frozen=True)
class EfeitoSalvo:
    nome: str
    titulo: str
    frase: str
    efeito: str
    meu: bool = False

    def para_json(self) -> dict:
        return asdict(self)


def _pronto(nome: str, titulo: str, frase: str, efeito: str) -> EfeitoSalvo:
    return EfeitoSalvo(nome, titulo, frase, normalizar(efeito))


PRONTOS = {p.nome: p for p in (
    _pronto("robo", "Robô", "Metálico e sem entonação, com o zumbido de um robô.",
            "robo=85,tom=-2,medios=3"),
    _pronto("esquilo", "Esquilo", "A voz de desenho animado: bem mais aguda e fina.",
            "tom=9,agudos=2"),
    _pronto("fofo", "Fofo", "Mais aguda e suave.", "tom=4,agudos=3"),
    _pronto("monstro", "Monstro", "Grave, rouca e com eco de caverna.",
            "tom=-8,distorcao=25,graves=6,sala=35"),
    _pronto("cantado", "Cantado", "Afinada nota a nota, como um autotune.", "afinacao=100"),
    _pronto("radio-antigo", "Rádio antigo", "A faixa estreita e o chiado de um rádio velho.",
            "radio=85,distorcao=20"),
    _pronto("telefone", "Telefone", "Como numa ligação.", "radio=65,medios=4"),
    _pronto("megafone", "Megafone", "Estourada e anasalada, de alto-falante.",
            "radio=60,distorcao=60,medios=5"),
    _pronto("fantasma", "Fantasma", "Sussurrada, trêmula e com eco.",
            "sussurro=60,vibrato=40,eco=45,sala=55"),
    _pronto("alienigena", "Alienígena", "Metálica, trêmula e um pouco mais aguda.",
            "tom=3,robo=40,vibrato=55"),
    _pronto("caverna", "Caverna", "Eco longo, como num lugar grande e vazio.",
            "eco=55,sala=75"),
    _pronto("gigante", "Gigante", "Grave e encorpada, com um pouco de sala.",
            "tom=-5,graves=6,sala=30"),
    _pronto("sussurro", "Sussurro", "Só o ar, sem a voz.", "sussurro=100"),
)}

ARQUIVO = "efeitos-de-voz.json"
TETO = 50
TITULO_MAXIMO = 40
FRASE_MAXIMA = 120


class EfeitoJaExiste(EfeitoInvalido):
    """Já há um efeito seu com esse nome (salvar de novo substitui, se pedido)."""


class EfeitoNaoExiste(EfeitoInvalido):
    """O efeito pedido não está entre os seus (ou é um pronto, que não muda)."""


def arquivo_dos_meus() -> Path:
    from editor.ia import pasta_de_dados

    return pasta_de_dados() / ARQUIVO


def conferir(dados) -> EfeitoSalvo:
    """Um efeito de quem usa: o nome (que não pode ser o de um pronto) e os ajustes."""
    from editor.presets import apelido

    if not isinstance(dados, dict):
        raise EfeitoInvalido("Isso não é um efeito.")
    titulo = re.sub(r"\s+", " ", str(dados.get("titulo") or "")).strip()
    if not titulo:
        raise EfeitoInvalido("Dê um nome ao efeito.")
    if len(titulo) > TITULO_MAXIMO:
        raise EfeitoInvalido(f"O nome passa de {TITULO_MAXIMO} letras.")
    nome = apelido(titulo)
    if not nome:
        raise EfeitoInvalido("O nome precisa de pelo menos uma letra ou um número.")
    if nome in PRONTOS or nome in {apelido(p.titulo) for p in PRONTOS.values()}:
        raise EfeitoInvalido(f"“{titulo}” é o nome de um efeito pronto: escolha outro.")
    efeito = normalizar(str(dados.get("efeito") or ""))
    if not efeito:
        raise EfeitoInvalido("Esse efeito não muda nada: mexa em pelo menos um controle.")
    frase = re.sub(r"\s+", " ", str(dados.get("frase") or "")).strip()[:FRASE_MAXIMA]
    return EfeitoSalvo(nome, titulo, frase or "Um efeito seu.", efeito, meu=True)


def meus() -> list[EfeitoSalvo]:
    """Os efeitos de quem usa, na ordem em que foram criados. Um arquivo estragado (ou um
    efeito que não passa mais nas conferências) é deixado de lado, com um aviso."""
    try:
        dados = json.loads(arquivo_dos_meus().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, ValueError) as erro:
        logger.warning("os seus efeitos de voz não puderam ser lidos (%s)", erro)
        return []
    lista = []
    for item in dados.get("efeitos", []) if isinstance(dados, dict) else []:
        try:
            lista.append(conferir(item))
        except EfeitoInvalido as erro:
            logger.warning("um efeito de voz seu foi deixado de lado: %s", erro)
    return lista


def todos() -> dict[str, EfeitoSalvo]:
    """Os prontos e, depois, os de quem usa."""
    return {**PRONTOS, **{e.nome: e for e in meus()}}


def exportar(lista: list[EfeitoSalvo] | None = None) -> dict:
    """O arquivo dos efeitos de quem usa: o mesmo que fica no disco e que a importação lê."""
    return {"editor-de-video": "efeitos-de-voz", "versao": 1,
            "efeitos": [{"titulo": e.titulo, "frase": e.frase, "efeito": e.efeito}
                        for e in (meus() if lista is None else lista)]}


def _gravar(lista: list[EfeitoSalvo]) -> None:
    destino = arquivo_dos_meus()
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_suffix(".parcial")
    parcial.write_text(json.dumps(exportar(lista), ensure_ascii=False, indent=1),
                       encoding="utf-8")
    parcial.replace(destino)


def salvar(dados, *, substituir: bool = False) -> EfeitoSalvo:
    e = conferir(dados)
    atuais = meus()
    existe = any(x.nome == e.nome for x in atuais)
    if existe and not substituir:
        raise EfeitoJaExiste(f"Já existe um efeito seu chamado “{e.titulo}”.")
    if not existe and len(atuais) >= TETO:
        raise EfeitoInvalido(f"Cabem até {TETO} efeitos seus: apague um antes.")
    _gravar([e if x.nome == e.nome else x for x in atuais] if existe else [*atuais, e])
    return e


def atualizar(nome: str, dados) -> EfeitoSalvo:
    """Edita um efeito seu no mesmo lugar da lista; o título pode mudar (renomear), desde
    que o nome novo não seja o de um pronto nem o de outro seu."""
    atuais = meus()
    lugar = next((k for k, x in enumerate(atuais) if x.nome == nome), None)
    if lugar is None:
        raise EfeitoNaoExiste("Esse efeito não existe (ou não é seu).")
    e = conferir(dados)
    if e.nome != nome and any(x.nome == e.nome for x in atuais):
        raise EfeitoJaExiste(f"Já existe um efeito seu chamado “{e.titulo}”.")
    atuais[lugar] = e
    _gravar(atuais)
    return e


def apagar(nome: str) -> None:
    atuais = meus()
    if not any(x.nome == nome for x in atuais):
        raise EfeitoNaoExiste("Esse efeito não existe (ou não é seu).")
    _gravar([x for x in atuais if x.nome != nome])


def importar(dados) -> tuple[list[str], list[str]]:
    """Junta os efeitos de um arquivo exportado aos de quem usa (o mesmo nome substitui).
    Devolve os que entraram e os recusados, com o motivo."""
    lista = dados.get("efeitos") if isinstance(dados, dict) else dados
    if not isinstance(lista, list):
        raise EfeitoInvalido("Esse arquivo não tem efeitos de voz do editor.")
    atuais = {e.nome: e for e in meus()}
    entraram, recusados = [], []
    for item in lista[: TETO * 2]:
        titulo = str(item.get("titulo") or "?")[:TITULO_MAXIMO] if isinstance(item, dict) else "?"
        try:
            e = conferir(item)
        except EfeitoInvalido as erro:
            recusados.append(f"{titulo}: {erro}")
            continue
        if e.nome not in atuais and len(atuais) >= TETO:
            recusados.append(f"{titulo}: não cabe (até {TETO} efeitos seus)")
            continue
        atuais[e.nome] = e
        entraram.append(e.titulo)
    if entraram:
        _gravar(list(atuais.values()))
    return entraram, recusados


def resolver(nome_ou_ajustes: str) -> str:
    """O texto do efeito a partir de um nome (pronto ou seu, também pelo título) ou dos
    próprios ajustes (``tom=9,eco=30``)."""
    from editor.presets import apelido

    bruto = str(nome_ou_ajustes or "").strip()
    if not bruto:
        return ""
    if "=" in bruto:
        return normalizar(bruto)
    achado = todos().get(apelido(bruto))
    if achado is None:
        raise EfeitoInvalido(f"efeito desconhecido: {bruto} (use {', '.join(todos())}, ou "
                             "ajustes como tom=9,eco=30)")
    return achado.efeito


def para_json() -> dict:
    """O que a página precisa: os controles (faixas e grupos) e os efeitos, prontos e seus."""
    return {"controles": [asdict(c) for c in CONTROLES],
            "efeitos": [e.para_json() for e in todos().values()]}


__all__ = [
    "AMBIENTE",
    "CONTROLES",
    "PRONTOS",
    "TETO",
    "Controle",
    "EfeitoInvalido",
    "EfeitoJaExiste",
    "EfeitoNaoExiste",
    "EfeitoSalvo",
    "apagar",
    "aplicar",
    "aplicar_na_voz",
    "aplicar_no_ambiente",
    "arquivo_dos_meus",
    "atualizar",
    "conferir",
    "escrever",
    "exportar",
    "importar",
    "ler",
    "meus",
    "normalizar",
    "para_json",
    "previa",
    "resolver",
    "salvar",
    "todos",
    "trecho_para_ouvir",
]
