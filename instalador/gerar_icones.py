"""Os ícones do atalho que o instalador cria (``editor/recursos/icone``), desenhados do mesmo
``web/public/icone.svg`` da página: o adesivo amarelo inclinado com o "play".

    uv run python instalador/gerar_icones.py

Só precisa rodar de novo se o ícone mudar. Sai ``editai.png`` (Linux), ``editai.ico``
(Windows) e ``editai.icns`` (macOS).
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

AMARELO, TINTA = (255, 212, 0, 255), (26, 26, 26, 255)
DESTINO = Path(__file__).resolve().parents[1] / "editor" / "recursos" / "icone"


def desenhar(lado: int) -> Image.Image:
    """O SVG (caixa de 64) num quadrado de ``lado``, desenhado 4 vezes maior e reduzido."""
    k = lado * 4 / 64
    im = Image.new("RGBA", (lado * 4, lado * 4), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    # o retângulo: x 6, y 14, 52 × 36, cantos de 12, e o contorno de 5 centrado na borda, como
    # no SVG (o do PIL vai todo para dentro: a caixa cresce meio contorno de cada lado)
    d.rounded_rectangle([3.5 * k, 11.5 * k, 60.5 * k, 52.5 * k], radius=14.5 * k, fill=AMARELO,
                        outline=TINTA, width=round(5 * k))
    d.polygon([(27 * k, 24 * k), (27 * k, 40 * k), (40 * k, 32 * k)], fill=TINTA)
    im = im.rotate(6, resample=Image.BICUBIC, center=(32 * k, 32 * k))    # rotate(-6) do SVG
    return im.resize((lado, lado), Image.LANCZOS)


def main() -> None:
    DESTINO.mkdir(parents=True, exist_ok=True)
    grande = desenhar(1024)
    desenhar(512).save(DESTINO / "editai.png")
    grande.save(DESTINO / "editai.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
                                               (128, 128), (256, 256)])
    grande.save(DESTINO / "editai.icns")
    for f in sorted(DESTINO.iterdir()):
        print(f.name, f.stat().st_size)


if __name__ == "__main__":
    main()
