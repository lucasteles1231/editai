"""
A página da prova da IA local: as respostas de cada IA lado a lado, tarefa por tarefa, com o
tempo, os pedidos e a memória. Lê a pasta de ``comparar_ia.py`` e grava um HTML só (sem nada
de fora), para abrir no navegador.

    uv run python ferramentas/relatorio_da_prova.py --resultados prova/resultados \\
        --entradas e.json --saida prova/relatorio.html
"""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

#: A ordem das colunas e o nome de cada IA na página.
IAS = {"gemini": "Gemini (a chave grátis)", "qwen35": "Qwen3.5-4B", "gemma4e4b": "Gemma 4 E4B",
       "gemma4": "Gemma 4 E2B", "qwen3vl": "Qwen3-VL-4B",
       "qwen35-sem-placa": "Qwen3.5-4B, sem placa", "gemma4-sem-placa": "Gemma 4 E2B, sem placa",
       "gemini-lote4": "Gemini, 4 cenas por pedido", "qwen35-lote4": "Qwen3.5-4B, 4 por pedido",
       "gemma4e4b-lote4": "Gemma 4 E4B, 4 por pedido", "gemma4-lote4": "Gemma 4 E2B, 4 por pedido"}
#: O nome de cada tarefa, pelo começo do nome do arquivo.
TAREFAS = {"roteiro": "As cenas e os cartões de um vídeo falado",
           "thumbnail": "As ideias de thumbnail (8 quadros)",
           "matriz": "A matriz das cenas (as fotos e os clipes de uma biblioteca)",
           "avatar": "O avatar pela foto", "tema": "O roteiro pelo tema",
           "buscas": "As buscas das fotos de um roteiro",
           "duracao": "As frases que ficam num corte para 45 s",
           "pesquisa": "O roteiro de uma notícia, com a pesquisa na internet"}

CSS = """
:root{--fundo:#f6f5f2;--cartao:#fff;--texto:#1d1f24;--fraco:#5d636e;--linha:#dedbd4;
--bom:#1f7a4d;--ruim:#b3261e;--realce:#2f5d9e}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--fundo:#16181c;--cartao:#1f2228;
--texto:#e8e6e1;--fraco:#a0a6b0;--linha:#33373f;--bom:#5ccf8f;--ruim:#ff8a80;--realce:#8fb4ff}}
*{box-sizing:border-box}body{margin:0;background:var(--fundo);color:var(--texto);
font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1500px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:26px;margin:0 0 4px}h2{font-size:19px;margin:36px 0 8px}
h3{font-size:15px;margin:0 0 6px}.fraco{color:var(--fraco)}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}
th,td{border-bottom:1px solid var(--linha);padding:6px 8px;text-align:left;vertical-align:top}
.rolar{overflow-x:auto}.ok{color:var(--bom);font-weight:600}.nao{color:var(--ruim);font-weight:600}
.grade{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(300px,1fr))}
.cartao{background:var(--cartao);border:1px solid var(--linha);border-radius:8px;padding:12px}
.cartao ul{margin:4px 0;padding-left:18px}.cartao p{margin:4px 0}
.medida{font-size:13px;color:var(--fraco);margin-bottom:6px}
details{margin-top:6px}summary{cursor:pointer;color:var(--realce)}
pre{white-space:pre-wrap;font-size:12px;max-height:320px;overflow:auto}
"""


def _e(x) -> str:
    return html.escape(str(x if x is not None else ""))


def _medida(r: dict) -> str:
    partes = [f"{r.get('segundos', 0):.0f} s".replace(".", ","),
              f"{len(r.get('chamadas', []))} pedido(s)"]
    if r.get("memoria_mb"):
        partes.append(f"{r['memoria_mb'] / 1024:.1f} GB".replace(".", ","))
    estado = ('<span class="ok">passou</span>' if r.get("ok")
              else '<span class="nao">não passou</span>')
    return f'<div class="medida">{estado} · {" · ".join(partes)}</div>'


def _lista(itens) -> str:
    return "<ul>" + "".join(f"<li>{i}</li>" for i in itens) + "</ul>"


def _roteiro(r: dict, cenas: dict) -> str:
    resp = r.get("resposta") or {}
    cartoes = [f"<b>{_e(c.get('modelo'))}</b>: {_e(c.get('texto') or c.get('rotulo') or '')}"
               + (" — " + _e(", ".join(str(i.get("texto", "")) for i in c.get("itens", [])))
                  if c.get("itens") else "")
               for c in resp.get("cartoes", [])]
    blocos = [f"<i>“{_e(b['texto'][:70])}”</i> → "
              + _e("; ".join(cenas.get(i, i)[:60] for i in b.get("cenas", [])[:2]))
              for b in resp.get("blocos", [])[:6]]
    return (f"<p>{r.get('cartoes', 0)} cartões, {r.get('cenas', 0)} cenas</p>"
            f"<h3>Os cartões</h3>{_lista(cartoes) if cartoes else '<p>nenhum</p>'}"
            f"<h3>As primeiras cenas</h3>{_lista(blocos)}")


def _thumbnail(r: dict) -> str:
    return _lista(f"<b>{_e(v.get('chamada'))}</b> ({_e(v.get('modelo'))}, fundo "
                  f"{_e(v.get('fundo'))}): {_e(v.get('ideia'))}"
                  for v in r.get("resposta") or [])


def _matriz(r: dict) -> str:
    cenas = r.get("resposta") or []
    return (f"<p>{r.get('descritas', 0)} de {r.get('total', 0)} descritas</p>"
            + _lista(f"{_e(c.get('descricao'))} <span class='fraco'>("
                     f"{_e(', '.join(c.get('categorias') or []))}; {_e(c.get('energia'))})</span>"
                     for c in cenas[:12]))


def _avatar(r: dict) -> str:
    resp = r.get("resposta") or {}
    escolhas = resp.get("escolhas") or {}
    cores = escolhas.get("cores") or {}
    partes = [f"{_e(k)}: {_e(v)}" for k, v in escolhas.items() if k != "cores" and v]
    return (f"<p>{_e(resp.get('descricao'))}</p>{_lista(partes)}"
            f"<p class='fraco'>cores: {_e(', '.join(f'{k} {v}' for k, v in cores.items()))}</p>")


def _tema(r: dict) -> str:
    resp = r.get("resposta") or {}
    alvo = f" (o alvo era {r['alvo']})" if r.get("alvo") else ""
    problemas = (_lista(_e(p) for p in r["problemas"]) if r.get("problemas") else "")
    return (f"<p><b>{_e(resp.get('titulo'))}</b> · {r.get('palavras', 0)} palavras{alvo}</p>"
            f"{problemas}" + "".join(f"<p>{_e(p)}</p>" for p in resp.get("paragrafos", [])))


def _buscas(r: dict) -> str:
    return _lista(f"<b>{_e(b.get('termo'))}</b> · reserva {_e(b.get('reserva'))} · "
                  f"<span class='fraco'>{_e(b.get('descricao'))}</span>"
                  for b in (r.get("resposta") or [])[:10])


def _duracao(r: dict) -> str:
    resp = r.get("resposta") or {}
    fora = resp.get("fora") or []
    return (f"<p>{r.get('antes', 0)} s → {r.get('depois', 0)} s"
            f"{' · ' + _e(r['aviso']) if r.get('aviso') else ''}</p>"
            f"<h3>O que saiu ({len(fora)} frases)</h3>"
            + _lista(_e(f["texto"]) for f in fora[:12]))


def _pesquisa(r: dict) -> str:
    resp = r.get("resposta") or {}
    feitas = (r.get("pesquisa") or {}).get("feitas", [])
    buscas = _lista(_e(f"{f['ferramenta']}: {f.get('consulta') or f.get('link', '')}"
                       + (f" ({f['erro']})" if f.get("erro") else ""))
                    for f in feitas)
    return (f"<p>{r.get('buscas_da_ia', 0)} busca(s) e leitura(s) pedidas pela IA</p>"
            f"<h3>O que foi buscado</h3>{buscas}<h3>As notas</h3><pre>{_e(r.get('notas'))}</pre>"
            f"<h3>{_e(resp.get('titulo'))}</h3>"
            + "".join(f"<p>{_e(p)}</p>" for p in resp.get("paragrafos", [])))


def _conteudo(tipo: str, r: dict, cenas: dict) -> str:
    if r.get("erro"):
        return f"<p class='nao'>{_e(r['erro'])}</p>"
    corpo = {"roteiro": lambda: _roteiro(r, cenas), "thumbnail": lambda: _thumbnail(r),
             "matriz": lambda: _matriz(r), "avatar": lambda: _avatar(r),
             "tema": lambda: _tema(r), "buscas": lambda: _buscas(r),
             "duracao": lambda: _duracao(r), "pesquisa": lambda: _pesquisa(r)}[tipo]()
    return corpo + (f"<details><summary>os pedidos</summary><pre>"
                    f"{_e(json.dumps(r.get('chamadas'), ensure_ascii=False, indent=1))}</pre>"
                    "</details>")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--resultados", type=Path, required=True)
    p.add_argument("--entradas", type=Path, required=True)
    p.add_argument("--saida", type=Path, required=True)
    a = p.parse_args(argv)
    entradas = json.loads(a.entradas.read_text(encoding="utf-8"))
    biblioteca = Path(entradas["biblioteca"]) / "cenas.json"
    cenas = {c.get("id") or Path(c["arquivo"]).stem: c["descricao"]
             for c in json.loads(biblioteca.read_text(encoding="utf-8"))}
    ias = [i for i in IAS if (a.resultados / i).is_dir()]
    respostas: dict[str, dict[str, dict]] = {}
    for ia in ias:
        for arquivo in sorted((a.resultados / ia).glob("*.json")):
            if arquivo.name == "resumo.json":
                continue
            r = json.loads(arquivo.read_text(encoding="utf-8"))
            respostas.setdefault(r["tarefa"], {})[ia] = r
    ordem = sorted(respostas, key=lambda t: (list(TAREFAS).index(t.split("-")[0]), t))
    linhas = []
    for t in ordem:
        celulas = []
        for ia in ias:
            r = respostas[t].get(ia)
            if r is None:
                celulas.append("<td class='fraco'>—</td>")
                continue
            marca = "ok" if r.get("ok") else "nao"
            celulas.append(f"<td><span class='{marca}'>{'✓' if r.get('ok') else '✗'}</span> "
                           f"{r.get('segundos', 0):.0f} s</td>")
        linhas.append(f"<tr><th><a href='#{_e(t)}'>{_e(t)}</a></th>{''.join(celulas)}</tr>")
    secoes = []
    for t in ordem:
        tipo = t.split("-")[0]
        cartoes = "".join(
            f"<div class='cartao'><h3>{_e(IAS[ia])}</h3>{_medida(respostas[t][ia])}"
            f"{_conteudo(tipo, respostas[t][ia], cenas)}</div>"
            for ia in ias if ia in respostas[t])
        secoes.append(f"<h2 id='{_e(t)}'>{_e(TAREFAS[tipo])} · <span class='fraco'>{_e(t)}"
                      f"</span></h2><div class='grade'>{cartoes}</div>")
    pagina = f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>A prova da IA local</title>
<style>{CSS}</style></head><body><main>
<h1>A prova da IA local</h1>
<p class="fraco">As tarefas do Editai que hoje vão ao Gemini, nos modelos locais (pelo
llama-server, num MacBook M5 de 16 GB) e no Gemini, com as mesmas entradas. ✓ quer dizer que a
resposta passou na conferência do próprio editor; o resto é você quem julga.</p>
<div class="rolar"><table><thead><tr><th>tarefa</th>
{''.join(f'<th>{_e(IAS[i])}</th>' for i in ias)}</tr></thead><tbody>{''.join(linhas)}</tbody>
</table></div>
{''.join(secoes)}
</main></body></html>"""
    a.saida.write_text(pagina, encoding="utf-8")
    print(a.saida)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
