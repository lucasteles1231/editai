"""
A voz local. Roda no ambiente dela (``<dados>/voz-local/.venv``), e não no do editor: só
precisa do ``piper-tts`` (GPL-3, por isso à parte; ver ``editor/voz_local.py``).

    python -I voz_local.py --conferir MODELO     carrega a voz e lê uma frase de teste
    python -I voz_local.py PEDIDO.json           gera as frases do pedido

Cada linha do stdout é um JSON: ``{"feitas": 3, "total": 9}`` a cada frase pronta. Os erros vão
para o stderr.
"""
from __future__ import annotations

import json
import sys
import tempfile
import wave
from pathlib import Path


def avisar(**dados) -> None:
    # Só ASCII: com o -I, o PYTHONIOENCODING é ignorado, e o stdout do Windows é cp1252.
    print(json.dumps(dados), flush=True)


def carregar(modelo: str):
    from piper import PiperVoice

    return PiperVoice.load(modelo)


def ler(voz, texto: str, saida: str) -> None:
    with wave.open(saida, "wb") as w:
        voz.synthesize_wav(texto, w)


def conferir(modelo: str) -> None:
    voz = carregar(modelo)
    with tempfile.TemporaryDirectory() as tmp:
        saida = str(Path(tmp) / "teste.wav")
        ler(voz, "Olá! Esta é a voz local do Editai.", saida)
        with wave.open(saida, "rb") as w:
            segundos = w.getnframes() / max(1, w.getframerate())
    if segundos < 0.5:
        raise SystemExit("a frase de teste saiu vazia")
    avisar(ok=True, segundos=round(segundos, 2))


def gerar(arquivo: str) -> None:
    pedido = json.loads(Path(arquivo).read_text(encoding="utf-8"))
    voz = carregar(pedido["modelo"])
    frases = pedido["frases"]
    for k, frase in enumerate(frases):
        parcial = frase["saida"] + ".parcial.wav"
        ler(voz, frase["texto"], parcial)
        Path(parcial).replace(frase["saida"])
        avisar(feitas=k + 1, total=len(frases))


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--conferir":
        conferir(sys.argv[2])
    elif len(sys.argv) == 2:
        gerar(sys.argv[1])
    else:
        raise SystemExit(__doc__)
