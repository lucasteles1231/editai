"""
O auditor de verdade: baixa o SigLIP 2 (uns 410 MB, conferidos pelo SHA-256), calcula os
textos no processo à parte e dá a nota de duas imagens. O workflow manual ``modelos.yml`` roda
isto no Windows e no Mac: é o que os testes comuns não cobrem (eles usam um auditor falso).

    uv run python tests/auditor_de_verdade.py

O pytest não coleta este arquivo: ele baixa o modelo.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from editor import auditor


def _ceu() -> Image.Image:
    img = Image.new("RGB", (640, 480), (90, 160, 235))
    desenho = ImageDraw.Draw(img)
    for x, y in ((120, 120), (380, 90), (500, 220)):
        desenho.ellipse((x, y, x + 140, y + 60), fill=(250, 250, 250))
    return img


def _vermelho() -> Image.Image:
    img = Image.new("RGB", (640, 480), (20, 20, 20))
    ImageDraw.Draw(img).ellipse((170, 90, 470, 390), fill=(220, 20, 30))
    return img


def main() -> int:
    os.environ.pop(auditor.VARIAVEL_FALSA, None)
    comeco = time.monotonic()
    if not auditor.preparar(["um céu azul com nuvens", "um círculo vermelho"]):
        print("FALHOU: o auditor não carregou", file=sys.stderr)
        return 1
    preparar = time.monotonic() - comeco
    imagens = [_ceu(), _vermelho()]
    comeco = time.monotonic()
    ceu = auditor.avaliar(imagens, "um céu azul com nuvens")
    vermelho = auditor.avaliar(imagens, "um círculo vermelho")
    avaliar = time.monotonic() - comeco
    print(f"SigLIP 2: preparou em {preparar:.1f} s (com o download na primeira vez), avaliou "
          f"em {avaliar:.1f} s; céu {ceu.notas}, vermelho {vermelho.notas}")
    falhas = []
    if not ceu.notas[0] > ceu.notas[1]:
        falhas.append("o céu não ganhou do círculo no texto do céu")
    if not vermelho.notas[1] > vermelho.notas[0]:
        falhas.append("o círculo não ganhou do céu no texto do círculo")
    if not auditor.baixado():
        falhas.append("o modelo não ficou no cache")
    auditor.soltar()
    for f in falhas:
        print(f"FALHOU: {f}", file=sys.stderr)
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
