"""
O gabarito do corte exato da palavra: os começos e os fins de palavra marcados à mão, no som,
para medir contra eles o Whisper (que adianta o começo em até 0,9 s) e o corte novo.

1. **Preparar:** o Whisper do Editai transcreve as gravações. A ferramenta escolhe uns 100
   pontos onde o editor corta: o começo de uma palavra depois de uma pausa e o fim de uma
   palavra antes de uma pausa. Para cada ponto, ela grava o trecho de som (1,4 s) e a figura
   (a forma de onda e o espectrograma, 1 ms por pixel).
2. **Marcar:** a página abre no navegador, servida só no ``127.0.0.1``. Cada marca é guardada
   na hora em ``gabarito.json``. O tempo que o Whisper deu não aparece, para não puxar o olho, e
   o trecho começa num deslocamento sorteado, para a palavra não cair sempre no mesmo lugar.
3. **Revisar:** ``--revisar fim`` (ou ``comeco``, ou os números separados por vírgula) passa só
   pelas marcas já feitas, com a marca de antes na figura.

    uv run python ferramentas/marcar_palavras.py --saida ~/Movies/editor-de-video/gabarito \\
        ~/Movies/gravacao.mp4 ~/Library/"Application Support"/editor-de-video/vozes/*/leitura/*.wav

    uv run python ferramentas/marcar_palavras.py --saida ~/Movies/editor-de-video/gabarito --marcar

    uv run python ferramentas/marcar_palavras.py --saida ~/Movies/editor-de-video/gabarito \\
        --marcar --revisar fim

As gravações, as figuras e o gabarito ficam fora do repositório.
"""
from __future__ import annotations

import argparse
import contextlib
import http.server
import json
import sys
import threading
import wave
import webbrowser
from functools import partial
from pathlib import Path
from urllib.parse import quote, urlsplit

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from editor import componentes, transcricao
from editor import video as video_mod

TAXA = 48_000
#: O trecho de cada ponto, e quanto ele pode deslizar para os lados.
JANELA_S = 1.4
DESLIZE_S = 0.15
#: A pausa que conta como corte (o Editai corta acima de 0,45 s; abaixo disso, a legenda e a
#: escolha das frases também usam a fronteira).
PAUSA_S = 0.15
#: A figura: 1 ms por pixel; a forma de onda em cima, o espectrograma (até 12 kHz) embaixo.
LARGURA = int(JANELA_S * 1000)
ALTURA_DA_ONDA = 150
ALTURA_DO_ESPECTRO = 210
ATE_HZ = 12_000
#: A página de marcar (ao lado deste arquivo), servida daqui mesmo: uma correção nela vale para
#: o gabarito já preparado.
PAGINA = Path(__file__).with_suffix(".html")


def _gravar(caminho: Path, x: np.ndarray) -> None:
    with wave.open(str(caminho), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(TAXA)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


def _cores(v: np.ndarray) -> np.ndarray:
    """Do escuro ao claro, passando pelo roxo e pelo laranja (0 a 1 → RGB)."""
    pontos = np.array([0.0, 0.3, 0.6, 0.85, 1.0])
    cores = np.array([[10, 8, 30], [80, 20, 110], [200, 60, 80], [250, 160, 60], [255, 245, 200]])
    v = np.clip(v, 0, 1)
    return np.stack([np.interp(v, pontos, cores[:, c]) for c in range(3)], axis=-1).astype(np.uint8)


def figura(x: np.ndarray, caminho: Path) -> None:
    """A forma de onda e o espectrograma do trecho, 1 ms por pixel."""
    n = len(x)
    passo = n / LARGURA
    onda = Image.new("RGB", (LARGURA, ALTURA_DA_ONDA), (250, 250, 247))
    desenho = ImageDraw.Draw(onda)
    meio = ALTURA_DA_ONDA / 2
    pico = max(float(np.abs(x).max()), 1e-4)
    for px in range(LARGURA):
        trecho = x[int(px * passo):max(int(px * passo) + 1, int((px + 1) * passo))]
        alto, baixo = float(trecho.max()), float(trecho.min())
        escala = (meio - 4) / pico
        desenho.line([(px, meio - alto * escala), (px, meio - baixo * escala)], fill=(40, 70, 120))
    desenho.line([(0, meio), (LARGURA, meio)], fill=(200, 200, 195))
    # o espectrograma: janelas de 10 ms a cada 1 ms
    janela = 480
    pad = np.concatenate([np.zeros(janela // 2, np.float32), x, np.zeros(janela, np.float32)])
    colunas = np.stack([pad[int(px * passo):int(px * passo) + janela] for px in range(LARGURA)])
    espectro = np.abs(np.fft.rfft(colunas * np.hanning(janela), axis=1))
    faixas = int(ATE_HZ / (TAXA / janela))
    db = 20 * np.log10(espectro[:, :faixas].T[::-1] + 1e-7)
    db = (db - (db.max() - 70)) / 70
    imagem = Image.fromarray(_cores(db)).resize((LARGURA, ALTURA_DO_ESPECTRO), Image.BILINEAR)
    final = Image.new("RGB", (LARGURA, ALTURA_DA_ONDA + ALTURA_DO_ESPECTRO))
    final.paste(onda, (0, 0))
    final.paste(imagem, (0, ALTURA_DA_ONDA))
    final.save(caminho)


def pontos(palavras, duracao: float) -> list[dict]:
    """Os começos depois de uma pausa e os fins antes de uma pausa."""
    saida = []
    for i, w in enumerate(palavras):
        antes = w.inicio - (palavras[i - 1].fim if i else 0.0)
        depois = (palavras[i + 1].inicio if i + 1 < len(palavras) else duracao) - w.fim
        contexto = " ".join(p.texto for p in palavras[max(0, i - 3):i + 4])
        if antes >= PAUSA_S:
            saida.append({"tipo": "comeco", "palavra": w.texto, "whisper_s": w.inicio,
                          "contexto": contexto})
        if depois >= PAUSA_S:
            saida.append({"tipo": "fim", "palavra": w.texto, "whisper_s": w.fim,
                          "contexto": contexto})
    return saida


def preparar(gravacoes: list[Path], saida: Path, quantos: int, semente: int) -> int:
    componentes.aprovar([f"whisper-{transcricao.MODELO_PADRAO}"])   # já está no computador
    rng = np.random.default_rng(semente)
    (saida / "trechos").mkdir(parents=True, exist_ok=True)
    candidatos = []
    for g in gravacoes:
        x = video_mod.ler_audio_mono(g, TAXA).astype(np.float32)
        duracao = len(x) / TAXA
        palavras = transcricao.transcrever(g, duracao=duracao)
        achados = pontos(palavras, duracao)
        print(f"{g.name}: {len(palavras)} palavras, {len(achados)} pontos", flush=True)
        candidatos += [{**p, "arquivo": str(g)} for p in achados]
    rng.shuffle(candidatos)
    # metade começos, metade fins, enquanto houver
    comecos = [c for c in candidatos if c["tipo"] == "comeco"]
    fins = [c for c in candidatos if c["tipo"] == "fim"]
    escolhidos = comecos[: quantos // 2] + fins[: quantos - min(len(comecos), quantos // 2)]
    escolhidos = escolhidos[:quantos]
    rng.shuffle(escolhidos)
    audios: dict[str, np.ndarray] = {}
    marcas = []
    for k, c in enumerate(escolhidos):
        x = audios.setdefault(c["arquivo"], video_mod.ler_audio_mono(Path(c["arquivo"]), TAXA))
        # o Whisper adianta o começo e o fim: o de verdade costuma vir depois
        antes = 0.4 if c["tipo"] == "comeco" else 0.5
        inicio = max(0.0, c["whisper_s"] - antes + rng.uniform(-DESLIZE_S, DESLIZE_S))
        fim = min(len(x) / TAXA, inicio + JANELA_S)
        inicio = max(0.0, fim - JANELA_S)
        trecho = x[int(inicio * TAXA):int(fim * TAXA)].astype(np.float32)
        nome = f"{k:03d}"
        _gravar(saida / "trechos" / f"{nome}.wav", trecho)
        figura(trecho, saida / "trechos" / f"{nome}.png")
        marcas.append({"id": nome, "tipo": c["tipo"], "palavra": c["palavra"],
                       "contexto": c["contexto"], "arquivo": c["arquivo"],
                       "inicio_s": round(inicio, 4), "fim_s": round(fim, 4),
                       "whisper_s": round(c["whisper_s"], 4), "marca_s": None,
                       "pulado": False})
    (saida / "pontos.json").write_text(json.dumps(marcas, ensure_ascii=False, indent=1), "utf-8")
    print(f"{len(marcas)} pontos em {saida} ({sum(m['tipo'] == 'comeco' for m in marcas)} "
          "começos)")
    return 0


class _Servidor(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:
        pass

    def do_GET(self) -> None:
        if urlsplit(self.path).path not in ("/", "/index.html"):
            super().do_GET()
            return
        pagina = PAGINA.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(pagina)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(pagina)

    def do_POST(self) -> None:
        if self.path != "/salvar":
            self.send_error(404)
            return
        dados = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or "[]")
        pasta = Path(self.directory)
        temporario = pasta / "gabarito.json.parcial"
        temporario.write_text(json.dumps(dados, ensure_ascii=False, indent=1), "utf-8")
        temporario.replace(pasta / "gabarito.json")
        self.send_response(204)
        self.end_headers()


def marcar(saida: Path, porta: int, revisar: str | None = None) -> int:
    servidor = http.server.ThreadingHTTPServer(("127.0.0.1", porta),
                                               partial(_Servidor, directory=str(saida)))
    endereco = f"http://127.0.0.1:{porta}/index.html"
    if revisar:
        endereco += f"?revisar={quote(revisar)}"
    print(f"a página: {endereco} (Ctrl+C para fechar)")
    print(f"as marcas ficam em {saida / 'gabarito.json'}")
    threading.Timer(0.5, lambda: webbrowser.open(endereco)).start()
    with contextlib.suppress(KeyboardInterrupt):
        servidor.serve_forever()
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("gravacoes", type=Path, nargs="*")
    p.add_argument("--saida", type=Path, required=True)
    p.add_argument("--quantos", type=int, default=100)
    p.add_argument("--semente", type=int, default=7)
    p.add_argument("--marcar", action="store_true", help="só abre a página (já preparada)")
    p.add_argument("--porta", type=int, default=8765)
    p.add_argument("--revisar", help="fim, comeco ou os números (000,013): revê marcas já feitas")
    a = p.parse_args(argv)
    saida = a.saida.expanduser()
    if a.gravacoes:
        preparar([g.expanduser() for g in a.gravacoes], saida, a.quantos, a.semente)
    if a.marcar:
        return marcar(saida, a.porta, a.revisar)
    return 0


if __name__ == "__main__":
    sys.exit(main())
