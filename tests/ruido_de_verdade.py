"""
O redutor de ruído de verdade: baixa o DeepFilterNet3 (13 MB, conferidos pelo SHA-256), limpa
uma fala sintética com chiado e confere que a saída fica no mesmo tempo da entrada e que o
chiado saiu. O workflow manual ``modelos.yml`` roda isto no Windows e no Mac: é o que os testes
comuns não cobrem (eles usam um redutor falso).

    uv run python tests/ruido_de_verdade.py

O pytest não coleta este arquivo: ele baixa o modelo.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from editor import componentes, ruido
from tests.test_ruido import _com_ruido, _para_48k
from tests.test_sincronia import fala


def _si_sdr(referencia: np.ndarray, estimada: np.ndarray) -> float:
    r, e = referencia.astype(np.float64), estimada.astype(np.float64)
    r, e = r - r.mean(), e - e.mean()
    alvo = np.dot(e, r) / np.dot(r, r) * r
    return float(10 * np.log10(np.dot(alvo, alvo) / np.dot(e - alvo, e - alvo)))


def _atraso(saida: np.ndarray, entrada: np.ndarray, busca: int = 4800) -> int:
    n = len(entrada)
    tamanho = 1 << (2 * n - 1).bit_length()
    c = np.fft.irfft(np.fft.rfft(saida, tamanho) * np.conj(np.fft.rfft(entrada, tamanho)),
                     tamanho)
    return int(np.argmax(np.concatenate([c[-busca:], c[:busca + 1]]))) - busca


def main() -> int:
    os.environ.pop(ruido.VARIAVEL_FALSA, None)
    componentes.aprovar(["ruido"])          # quem usa disse "Aprovar e baixar"
    comeco = time.monotonic()
    componentes.baixar("ruido")
    baixar = time.monotonic() - comeco
    limpa = _para_48k(fala(10.0, semente=2))
    suja = _com_ruido(10.0, snr_db=5.0)
    comeco = time.monotonic()
    saida = ruido.limpar(suja, "forte")
    limpar = time.monotonic() - comeco
    ganho = _si_sdr(limpa, saida) - _si_sdr(limpa, suja)
    atraso = _atraso(ruido.limpar(limpa, "forte"), limpa)
    print(f"DeepFilterNet3: baixou em {baixar:.1f} s, limpou 10 s em {limpar:.1f} s; o SI-SDR "
          f"subiu {ganho:+.1f} dB, e a saída ficou {atraso} amostras fora do tempo")
    falhas = []
    # A fala daqui é sintética (tons com sopro, não voz), e o modelo aprendeu com voz: num M5,
    # ela subiu 5,1 dB (a voz Faber, na prova, de 6 a 18). O que importa aqui é que ele limpa.
    if ganho < 3:
        falhas.append(f"o chiado quase não saiu ({ganho:+.1f} dB)")
    if abs(atraso) > 2:
        falhas.append(f"a saída saiu {atraso} amostras fora do tempo da entrada")
    if len(saida) != len(suja) or not np.isfinite(saida).all():
        falhas.append("a saída mudou de tamanho ou tem nan")
    if not ruido.instalado():
        falhas.append("o modelo não ficou no computador")
    ruido.soltar()
    for f in falhas:
        print(f"FALHOU: {f}", file=sys.stderr)
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
