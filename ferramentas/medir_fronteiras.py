"""
A régua do corte exato da palavra: cada método contra o gabarito marcado à mão
(``ferramentas/marcar_palavras.py``).

Os métodos: **whisper**, o tempo cru do Whisper, e **novo**, o ``editor/fronteiras.py``. No
gabarito de 31/10/2026, a busca de pausa que o corte de silêncio usava antes dele acertava 41%
dos pontos da prova dentro de 30 ms (o pior erro, 667 ms); o Whisper cru, 14%.

**O ajuste e a prova ficam separados.** Os pontos com o número abaixo de ``--separar`` servem
para ajustar o método; os de cima só são marcados depois do ajuste, e a nota deles é a que vale
(ajustar e medir nos mesmos pontos dá uma nota otimista).

    uv run python ferramentas/medir_fronteiras.py --saida ~/Movies/editor-de-video/gabarito-palavras

O erro é o tempo do método menos a marca. **O que come a palavra** é o começo marcado depois do
de verdade, ou o fim antes, por mais de 20 ms: cortar ali tira o som da palavra.

Os pontos também saem separados pelo vão que o Whisper deu entre as duas palavras: acima de
``cortes.PAUSA_MAXIMA_S`` é onde o corte de silêncio corta; abaixo, a fala corrida (a vírgula),
que pesa na legenda e na escolha das frases.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from editor import componentes, cortes, fronteiras, transcricao
from editor import video as video_mod
from editor.transcricao import Palavra

TAXA = video_mod.TAXA
FAIXAS_MS = (10, 20, 30, 50, 100)
META_MS = 30
COME_A_PALAVRA_MS = 20


def _palavras(arquivo: Path, pasta: Path, duracao: float) -> list[Palavra]:
    """A transcrição do arquivo, guardada na pasta do gabarito (transcrever de novo leva
    minutos e dá o mesmo resultado)."""
    nome = hashlib.sha256(str(arquivo).encode()).hexdigest()[:10]
    guardada = pasta / "palavras" / f"{arquivo.stem}-{nome}.json"
    if guardada.exists():
        return [Palavra(**p) for p in json.loads(guardada.read_text("utf-8"))]
    componentes.aprovar([f"whisper-{transcricao.MODELO_PADRAO}"])
    palavras = transcricao.transcrever(arquivo, duracao=duracao)
    guardada.parent.mkdir(exist_ok=True)
    guardada.write_text(json.dumps([asdict(p) for p in palavras], ensure_ascii=False), "utf-8")
    return palavras


def _achar(palavras: list[Palavra], ponto: dict) -> int | None:
    """A palavra do ponto, pelo tempo que o Whisper deu a ela."""
    for i, p in enumerate(palavras):
        t = p.inicio if ponto["tipo"] == "comeco" else p.fim
        if abs(t - ponto["whisper_s"]) < 0.002 and p.texto == ponto["palavra"]:
            return i
    return None


def _vao(palavras: list[Palavra], i: int, tipo: str, duracao: float) -> float:
    """O vão que o Whisper deu entre a palavra e a vizinha do lado do ponto."""
    p = palavras[i]
    if tipo == "comeco":
        return p.inicio - (palavras[i - 1].fim if i else 0.0)
    return (palavras[i + 1].inicio if i + 1 < len(palavras) else duracao) - p.fim


def _metodos(palavras: list[Palavra], i: int, tipo: str, x: np.ndarray,
             duracao: float, medida: fronteiras.Atividade) -> dict[str, float]:
    p = palavras[i]
    anterior = palavras[i - 1] if i else None
    seguinte = palavras[i + 1] if i + 1 < len(palavras) else None
    if tipo == "comeco":
        return {"whisper": p.inicio, "novo": fronteiras.comeco(medida, p, anterior)}
    return {"whisper": p.fim, "novo": fronteiras.fim(medida, p, seguinte, duracao)}


def medir(pasta: Path, separar: int) -> dict:
    gabarito = json.loads((pasta / "gabarito.json").read_text("utf-8"))
    marcados = [m for m in gabarito if m.get("marca_s") is not None and not m.get("pulado")]
    audios: dict[str, np.ndarray] = {}
    transcricoes: dict[str, list[Palavra]] = {}
    medidas: dict[str, fronteiras.Atividade] = {}
    linhas = []
    for m in marcados:
        arquivo = Path(m["arquivo"])
        if m["arquivo"] not in audios:
            audios[m["arquivo"]] = video_mod.ler_audio_mono(arquivo, TAXA).astype(np.float32)
            medidas[m["arquivo"]] = fronteiras.atividade(audios[m["arquivo"]], TAXA)
        x = audios[m["arquivo"]]
        duracao = len(x) / TAXA
        if m["arquivo"] not in transcricoes:
            transcricoes[m["arquivo"]] = _palavras(arquivo, pasta, duracao)
        palavras = transcricoes[m["arquivo"]]
        i = _achar(palavras, m)
        if i is None:
            print(f"{m['id']}: '{m['palavra']}' não está na transcrição de agora", flush=True)
            continue
        tempos = _metodos(palavras, i, m["tipo"], x, duracao, medidas[m["arquivo"]])
        linhas.append({"id": m["id"], "tipo": m["tipo"], "palavra": m["palavra"],
                       "grupo": "ajuste" if int(m["id"]) < separar else "prova",
                       "vao_s": round(_vao(palavras, i, m["tipo"], duracao), 3),
                       "erros_ms": {k: round((v - m["marca_s"]) * 1000, 1)
                                    for k, v in tempos.items()}})
    return {"linhas": linhas}


def _come(tipo: str, erro: float) -> bool:
    return erro > COME_A_PALAVRA_MS if tipo == "comeco" else erro < -COME_A_PALAVRA_MS


def resumo(linhas: list[dict], metodo: str) -> dict:
    erros = np.array([abs(linha["erros_ms"][metodo]) for linha in linhas])
    if not len(erros):
        return {}
    return {"n": len(erros),
            **{f"ate_{f}": round(float(np.mean(erros <= f)) * 100) for f in FAIXAS_MS},
            "mediana": round(float(np.median(erros))),
            "p90": round(float(np.percentile(erros, 90))),
            "pior": round(float(erros.max())),
            "come": sum(_come(linha["tipo"], linha["erros_ms"][metodo]) for linha in linhas)}


def imprimir(linhas: list[dict]) -> None:
    for grupo in ("ajuste", "prova"):
        do_grupo = [linha for linha in linhas if linha["grupo"] == grupo]
        if not do_grupo:
            continue
        print(f"\n{grupo} ({len(do_grupo)} pontos)")
        print(f"{'método':<8} {'pontos':<17} " + " ".join(f"≤{f:>3}" for f in FAIXAS_MS)
              + "   med   p90  pior  come")
        corte = cortes.PAUSA_MAXIMA_S
        recortes = {
            "todos": lambda x: True,
            "comeco": lambda x: x["tipo"] == "comeco",
            "fim": lambda x: x["tipo"] == "fim",
            f"vão > {corte:g} s": lambda x: x["vao_s"] > cortes.PAUSA_MAXIMA_S,
            f"vão ≤ {corte:g} s": lambda x: x["vao_s"] <= cortes.PAUSA_MAXIMA_S,
        }
        for metodo in ("whisper", "novo"):
            for nome, filtro in recortes.items():
                sel = [x for x in do_grupo if filtro(x)]
                r = resumo(sel, metodo)
                if not r:
                    continue
                print(f"{metodo:<8} {nome:<13}{r['n']:>3}  "
                      + " ".join(f"{r[f'ate_{f}']:>3}%" for f in FAIXAS_MS)
                      + f" {r['mediana']:>5} {r['p90']:>5} {r['pior']:>5} {r['come']:>5}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--saida", type=Path, required=True, help="a pasta do gabarito")
    p.add_argument("--separar", type=int, default=50,
                   help="os pontos abaixo deste número são de ajuste; os de cima, da prova")
    p.add_argument("--detalhe", action="store_true", help="o erro de cada ponto")
    a = p.parse_args(argv)
    pasta = a.saida.expanduser()
    resultado = medir(pasta, a.separar)
    (pasta / "medida.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=1),
                                       "utf-8")
    if a.detalhe:
        for linha in resultado["linhas"]:
            e = linha["erros_ms"]
            print(f"{linha['id']} {linha['tipo']:<6} {linha['palavra']:<16} "
                  f"whisper {e['whisper']:>7.1f}  novo {e['novo']:>7.1f}")
    imprimir(resultado["linhas"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
