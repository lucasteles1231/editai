"""
A prova do ruído: jeitos de tirar o ruído da fala, medidos nas mesmas entradas, para escolher o
do Editai pelo que se mede e pelo que se ouve.

**Os candidatos:**

- ``hoje``: o portão espectral de hoje (``voz.tirar_ruido``), em numpy;
- ``afftdn``: o redutor de ruído por FFT do FFmpeg, que já vem no PyAV;
- ``arnndn``: o RNNoise do FFmpeg, com um modelo dos ``rnnoise-models`` (``--rnnoise sh.rnnn``,
  o arquivo baixado à parte);
- ``deepfilter``: o DeepFilterNet3 em ONNX (o pacote ``deepfilter-stream``, só se estiver no
  ambiente).

**As entradas:**

- **a fala limpa:** frases da voz Faber (a voz local do Editai), juntadas;
- **os ruídos, feitos aqui:** o de fundo das gravações do dono (os trechos mais quietos delas),
  o ventilador (ruído marrom com o zumbido de 60 Hz), o teclado (cliques) e o burburinho (outras
  frases da Faber, baixas e abafadas), misturados à fala a 0, 5, 10 e 20 dB;
- **as gravações do dono** (``--gravacoes``), como vieram: para ouvir antes e depois.

**O que mede:** o quanto o SI-SDR sobe (a fala limpa é conhecida), o STOI (se o ``pystoi``
estiver no ambiente), os segundos para limpar um minuto de áudio e o atraso que cada um põe no
som, e grava os WAVs e a página ``relatorio.html`` para ouvir lado a lado.

**O atraso conta.** O ``afftdn`` devolve o som 25 ms atrasado, no mesmo comprimento: sem alinhar,
o SI-SDR dele desabava para −90 dB, como se ele apagasse a fala. Cada saída é alinhada à fala
limpa (a correlação em ±100 ms) antes de medir, e o atraso achado vai para a página: o que
entrar no Editai precisa compensá-lo, ou a voz sai fora do tempo da boca.

**O ``nan`` também conta.** O ``arnndn`` devolveu amostras ``nan`` de vez em quando (25 numa
chamada, nenhuma na seguinte, com a mesma entrada). Elas são contadas, trocadas por zero para
medir, e vão para a página: no vídeo, uma amostra ``nan`` vira estalo.

    uv run python ferramentas/comparar_ruido.py --saida ~/Movies/editor-de-video/prova-ruido \\
        --gravacoes ~/Movies/gravacao.mp4
"""
from __future__ import annotations

import argparse
import html
import json
import sys
import time
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from editor import video as video_mod
from editor import voz, voz_local

TAXA = voz.TAXA
SNRS = (0, 5, 10, 20)
FRASES = [
    "Hoje eu vou mostrar como o editor corta as pausas sozinho.",
    "A legenda aparece palavra por palavra, no tempo da fala.",
    "Custa três reais e cabe no bolso de qualquer pessoa.",
    "O vídeo sai pronto para o Shorts, o Reels e o TikTok.",
    "Na primeira vez, ele pergunta antes de baixar qualquer coisa.",
    "Quando o som está ruim, dá para limpar o chiado do fundo.",
    "Fale perto do microfone e longe do ventilador.",
    "Depois é só arrastar o arquivo e esperar a barra andar.",
]
VOZES_DO_BURBURINHO = [
    "Você viu o jogo de ontem? Foi uma loucura no final.",
    "Eu acho que vai chover hoje à tarde, leva o guarda-chuva.",
    "A reunião mudou para as três, avisa o pessoal.",
    "Esse café está frio, vou pedir outro no balcão.",
]


# ── as entradas ───────────────────────────────────────────────────────────
def _ler(caminho: Path) -> np.ndarray:
    return video_mod.ler_audio_mono(Path(caminho), TAXA).astype(np.float32)


def _gravar(caminho: Path, x: np.ndarray) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(caminho), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(TAXA)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


def _faber(frases: list[str], pasta: Path) -> list[np.ndarray]:
    pasta.mkdir(parents=True, exist_ok=True)
    pedidos = [(texto, pasta / f"{k:02d}.wav") for k, texto in enumerate(frases)]
    if not all(p.is_file() for _, p in pedidos):
        voz_local.sintetizar(pedidos)
    return [_ler(p) for _, p in pedidos]


def fala_limpa(pasta: Path) -> np.ndarray:
    pausa = np.zeros(int(0.4 * TAXA), np.float32)
    partes = []
    for x in _faber(FRASES, pasta / "faber"):
        partes += [x, pausa]
    return np.concatenate(partes)


def _ativo(x: np.ndarray) -> float:
    """O volume da fala (as janelas de 20 ms acima do piso): a pausa não conta."""
    n = int(0.02 * TAXA)
    janelas = x[: len(x) // n * n].reshape(-1, n)
    rms = np.sqrt((janelas.astype(np.float64) ** 2).mean(axis=1))
    return float(np.sqrt(np.mean(rms[rms > rms.max() * 0.05] ** 2)))


def ruido_de_fundo(gravacoes: list[Path], n: int) -> np.ndarray | None:
    """Os 10% de janelas mais quietas das gravações, juntadas e repetidas até ``n``."""
    pedacos = []
    for g in gravacoes:
        x = _ler(g)
        janela = int(0.05 * TAXA)
        janelas = x[: len(x) // janela * janela].reshape(-1, janela)
        rms = np.sqrt((janelas.astype(np.float64) ** 2).mean(axis=1))
        pedacos.append(janelas[rms <= np.percentile(rms, 10)].ravel())
    if not pedacos:
        return None
    base = np.concatenate(pedacos)
    return np.resize(base, n).astype(np.float32)


def ventilador(n: int, rng) -> np.ndarray:
    marrom = np.cumsum(rng.standard_normal(n))
    marrom = voz.filtrar((marrom / np.abs(marrom).max()).astype(np.float32), "highpass=f=40")
    t = np.arange(n) / TAXA
    zumbido = sum(np.sin(2 * np.pi * 60 * h * t) / h for h in (1, 2, 3, 5))
    return (marrom + 0.05 * zumbido).astype(np.float32)


def teclado(n: int, rng) -> np.ndarray:
    x = np.zeros(n, np.float32)
    t = 0.0
    while t < n / TAXA - 0.05:
        i, m = int(t * TAXA), int(0.012 * TAXA)
        clique = rng.standard_normal(m) * np.exp(-np.arange(m) / (0.002 * TAXA))
        x[i:i + m] += clique.astype(np.float32) * rng.uniform(0.4, 1.0)
        t += rng.exponential(0.15)
    return x


def burburinho(n: int, rng, pasta: Path) -> np.ndarray:
    vozes = _faber(VOZES_DO_BURBURINHO, pasta / "burburinho")
    x = np.zeros(n, np.float32)
    for v in vozes:
        for _ in range(3):
            i = int(rng.uniform(0, max(1, n - len(v))))
            x[i:i + len(v)] += v[: n - i] * rng.uniform(0.5, 1.0)
    return voz.filtrar(x, "lowpass=f=2500")


def misturar(limpa: np.ndarray, ruido: np.ndarray, snr_db: float) -> np.ndarray:
    ruido = ruido[: len(limpa)]
    alvo = _ativo(limpa) / 10 ** (snr_db / 20)
    atual = float(np.sqrt(np.mean(ruido.astype(np.float64) ** 2))) or 1.0
    x = limpa + ruido * (alvo / atual)
    return (x / max(1.0, float(np.abs(x).max()) / 0.95)).astype(np.float32)


# ── os candidatos ─────────────────────────────────────────────────────────
def candidatos(rnnoise: Path | None) -> dict:
    lista = {"hoje": voz.tirar_ruido,
             "afftdn": lambda x: voz.filtrar(x, "afftdn=nr=20:nf=-40:tn=1")}
    if rnnoise is not None:
        lista["arnndn"] = lambda x: voz.filtrar(x, f"arnndn=m={rnnoise}")
    try:
        from deepfilter_stream import Denoiser  # type: ignore[import-not-found]

        def deepfilter(x: np.ndarray) -> np.ndarray:
            d = Denoiser()
            y = np.concatenate([d.process(x, sr=TAXA), d.flush()])
            return y[: len(x)].astype(np.float32)

        lista["deepfilter"] = deepfilter
    except ImportError:
        pass
    return lista


# ── as medidas ────────────────────────────────────────────────────────────
def atraso(saida: np.ndarray, entrada: np.ndarray, busca_s: float = 0.1) -> int:
    """Quantas amostras a ``saida`` está atrasada em relação à ``entrada``."""
    n = min(len(saida), len(entrada), 20 * TAXA)
    a, b = saida[:n].astype(np.float64), entrada[:n].astype(np.float64)
    tamanho = 1 << (2 * n - 1).bit_length()
    c = np.fft.irfft(np.fft.rfft(a, tamanho) * np.conj(np.fft.rfft(b, tamanho)), tamanho)
    busca = int(busca_s * TAXA)
    janela = np.concatenate([c[-busca:], c[:busca + 1]])
    return int(np.argmax(janela)) - busca


def alinhar(saida: np.ndarray, atraso_: int) -> np.ndarray:
    if atraso_ > 0:
        return np.concatenate([saida[atraso_:], np.zeros(atraso_, saida.dtype)])
    if atraso_ < 0:
        return np.concatenate([np.zeros(-atraso_, saida.dtype), saida[:atraso_]])
    return saida



def si_sdr(referencia: np.ndarray, estimada: np.ndarray) -> float:
    """O SI-SDR em dB (o quanto da estimada é a fala, com o volume que for)."""
    n = min(len(referencia), len(estimada))
    r, e = referencia[:n].astype(np.float64), estimada[:n].astype(np.float64)
    r, e = r - r.mean(), e - e.mean()
    alvo = (np.dot(e, r) / max(np.dot(r, r), 1e-12)) * r
    erro = e - alvo
    return float(10 * np.log10(max(np.dot(alvo, alvo), 1e-12) / max(np.dot(erro, erro), 1e-12)))


def stoi(referencia: np.ndarray, estimada: np.ndarray) -> float | None:
    try:
        from pystoi import stoi as medir  # type: ignore[import-not-found]
    except ImportError:
        return None
    n = min(len(referencia), len(estimada))
    return float(medir(referencia[:n], estimada[:n], TAXA, extended=False))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--saida", type=Path, required=True)
    p.add_argument("--gravacoes", type=Path, nargs="*", default=[],
                   help="gravações de verdade, para tirar o ruído de fundo e para ouvir")
    p.add_argument("--rnnoise", type=Path, help="um modelo .rnnn dos rnnoise-models")
    p.add_argument("--segundos", type=float, default=60.0,
                   help="quanto de cada gravação de verdade entra para ouvir")
    a = p.parse_args(argv)
    rng = np.random.default_rng(31)
    saida = a.saida.expanduser()
    limpa = fala_limpa(saida / "entradas")
    n = len(limpa)
    ruidos = {"ventilador": ventilador(n, rng), "teclado": teclado(n, rng),
              "burburinho": burburinho(n, rng, saida / "entradas")}
    fundo = ruido_de_fundo([g.expanduser() for g in a.gravacoes], n)
    if fundo is not None:
        ruidos = {"o fundo das gravações": fundo, **ruidos}
    lista = candidatos(a.rnnoise.expanduser() if a.rnnoise else None)
    print(f"fala limpa: {n / TAXA:.1f} s · candidatos: {', '.join(lista)}")
    _gravar(saida / "audios" / "limpa.wav", limpa)

    resultados, tempos = [], {nome: [0.0, 0.0] for nome in lista}
    nans = dict.fromkeys(lista, 0)

    def sem_nan(nome: str, y: np.ndarray) -> np.ndarray:
        falhas = int(np.isnan(y).sum())
        nans[nome] += falhas
        return np.nan_to_num(y, nan=0.0) if falhas else y

    # o atraso de cada um, medido na fala limpa (sem ruído, a correlação não erra)
    atrasos = {nome: atraso(np.nan_to_num(limpar(limpa)), limpa) for nome, limpar in lista.items()}
    print("atraso de cada um (amostras):", atrasos)
    for nome_ruido, ruido in ruidos.items():
        for snr in SNRS:
            mix = misturar(limpa, ruido, snr)
            base = f"{nome_ruido.replace(' ', '-')}-{snr}db"
            _gravar(saida / "audios" / f"{base}-mistura.wav", mix)
            antes = si_sdr(limpa, mix)
            linha = {"ruido": nome_ruido, "snr": snr, "antes": round(antes, 2),
                     "stoi_antes": stoi(limpa, mix), "candidatos": {}}
            for nome, limpar in lista.items():
                comeco = time.perf_counter()
                y = alinhar(sem_nan(nome, limpar(mix)), atrasos[nome])
                gasto = time.perf_counter() - comeco
                tempos[nome][0] += gasto
                tempos[nome][1] += len(mix) / TAXA
                _gravar(saida / "audios" / f"{base}-{nome}.wav", y)
                linha["candidatos"][nome] = {"si_sdr": round(si_sdr(limpa, y), 2),
                                             "ganho": round(si_sdr(limpa, y) - antes, 2),
                                             "stoi": stoi(limpa, y)}
            resultados.append(linha)
            print(f"  {nome_ruido} a {snr} dB: " + ", ".join(
                f"{k} {v['ganho']:+.1f} dB" for k, v in linha["candidatos"].items()))

    reais = []
    for g in a.gravacoes:
        x = _ler(g.expanduser())[: int(a.segundos * TAXA)]
        base = g.stem.replace(" ", "-")
        _gravar(saida / "audios" / f"real-{base}-original.wav", x)
        for nome, limpar in lista.items():
            y = alinhar(sem_nan(nome, limpar(x)), atrasos[nome])
            _gravar(saida / "audios" / f"real-{base}-{nome}.wav", y)
        reais.append(base)

    velocidade = {k: round(g / max(m, 1e-9) * 60, 2) for k, (g, m) in tempos.items()}
    (saida / "resultados.json").write_text(json.dumps(
        {"candidatos": list(lista), "segundos_por_minuto": velocidade,
         "atraso_ms": {k: round(v / TAXA * 1000, 2) for k, v in atrasos.items()},
         "amostras_nan": nans,
         "resultados": resultados, "reais": reais}, ensure_ascii=False, indent=1), "utf-8")
    atraso_ms = {k: v / TAXA * 1000 for k, v in atrasos.items()}
    (saida / "relatorio.html").write_text(
        _pagina(list(lista), velocidade, atraso_ms, nans, resultados, reais), "utf-8")
    print("segundos para limpar 1 min:", velocidade)
    print("amostras nan:", nans)
    print(f"a página: {saida / 'relatorio.html'}")
    return 0


# ── a página ──────────────────────────────────────────────────────────────
CSS = """
:root{--fundo:#f5f6f4;--cartao:#fff;--texto:#1c1f1d;--fraco:#5f6661;--linha:#d9ddd8;
--bom:#1d7a46;--ruim:#b3261e;--realce:#2a5d8f}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--fundo:#151816;--cartao:#1e2220;
--texto:#e6e9e6;--fraco:#a2aaa4;--linha:#323834;--bom:#62d195;--ruim:#ff8a80;--realce:#8db8ff}}
*{box-sizing:border-box}body{margin:0;background:var(--fundo);color:var(--texto);
font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1200px;margin:0 auto;padding:24px 16px 64px}h1{font-size:26px;margin:0 0 4px}
h2{font-size:19px;margin:32px 0 8px}.fraco{color:var(--fraco)}
.rolar{overflow-x:auto}table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}
th,td{border-bottom:1px solid var(--linha);padding:6px 8px;text-align:left;vertical-align:middle}
.melhor{color:var(--bom);font-weight:700}audio{width:220px;height:32px}
"""


def _player(caminho: str) -> str:
    return f'<td><audio controls preload="none" src="{html.escape(caminho)}"></audio></td>'


def _pagina(nomes: list[str], velocidade: dict, atraso_ms: dict, nans: dict,
            resultados: list[dict], reais: list[str]) -> str:
    def esc(x) -> str:
        return html.escape(str(x))

    linhas = []
    for r in resultados:
        ganhos = {k: v["ganho"] for k, v in r["candidatos"].items()}
        melhor = max(ganhos, key=ganhos.get)
        celulas = "".join(
            f'<td class="{"melhor" if k == melhor else ""}">{v["ganho"]:+.1f} dB'
            + (f' · STOI {v["stoi"]:.2f}' if v["stoi"] is not None else "") + "</td>"
            for k, v in r["candidatos"].items())
        linhas.append(f"<tr><td>{esc(r['ruido'])}</td><td>{r['snr']} dB</td>"
                      f"<td>{r['antes']:+.1f} dB</td>{celulas}</tr>")
    cabeca = "".join(f"<th>{esc(n)}</th>" for n in nomes)
    ouvir = []
    for r in resultados:
        if r["snr"] != 5:
            continue
        base = f"{r['ruido'].replace(' ', '-')}-5db"
        players = "".join(_player(f"audios/{base}-{n}.wav") for n in nomes)
        ouvir.append(f"<tr><td>{esc(r['ruido'])}</td><td><audio controls preload=\"none\" "
                     f'src="audios/{esc(base)}-mistura.wav"></audio></td>{players}</tr>')
    reais_html = []
    for base in reais:
        players = "".join(_player(f"audios/real-{base}-{n}.wav") for n in nomes)
        reais_html.append(f"<tr><td>{esc(base)}</td><td><audio controls preload=\"none\" "
                          f'src="audios/real-{esc(base)}-original.wav"></audio></td>{players}</tr>')
    tempo = "".join(f"<li>{esc(k)}: {v:.2f} s, e põe {atraso_ms[k]:.1f} ms de atraso no som"
                    + (f" (<b>{nans[k]} amostras nan</b>, trocadas por zero)" if nans[k] else "")
                    + "</li>" for k, v in velocidade.items())
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Prova do ruído</title>
<style>{CSS}</style></head><body><main>
<h1>Prova do ruído</h1>
<p class="fraco">A fala limpa é da voz Faber, misturada a cada ruído. O número é o quanto o SI-SDR
subiu: mais é melhor. Em verde, o melhor de cada linha. Ouça a linha de 5 dB e as gravações de
verdade antes de decidir: o número não pega o som "metálico" que alguns deixam.</p>
<p><audio controls preload="none" src="audios/limpa.wav"></audio> a fala limpa</p>
<h2>Os números</h2><div class="rolar"><table><thead><tr><th>ruído</th><th>mistura</th>
<th>antes</th>{cabeca}</tr></thead><tbody>{''.join(linhas)}</tbody></table></div>
<h2>Os segundos para limpar 1 min de áudio (no processador)</h2><ul>{tempo}</ul>
<h2>Para ouvir: cada ruído a 5 dB</h2><div class="rolar"><table><thead><tr><th>ruído</th>
<th>a mistura</th>{cabeca}</tr></thead><tbody>{''.join(ouvir)}</tbody></table></div>
<h2>As gravações de verdade</h2><div class="rolar"><table><thead><tr><th>gravação</th>
<th>como veio</th>{cabeca}</tr></thead><tbody>{''.join(reais_html)}</tbody></table></div>
</main></body></html>"""


if __name__ == "__main__":
    sys.exit(main())
