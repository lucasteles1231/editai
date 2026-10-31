"""
A prova da IA local: as tarefas do Editai que hoje vão ao Gemini, rodadas num modelo local
(pelo ``llama-server`` do llama.cpp) e no Gemini, com as mesmas entradas. Ela mede o JSON (de
primeira, ou depois do conserto), o tempo e a memória, e guarda as respostas para comparar
lado a lado.

**O código das tarefas é o de verdade.** Só a porta de saída muda: ``ia._perguntar`` (por
onde passam todos os pedidos de texto e de imagem) vai para o modelo local. A conferência,
o conserto e a leitura da resposta são os mesmos do editor.

**As tarefas:**

1. ``roteiro``: as cenas e os cartões de um vídeo falado;
2. ``thumbnail``: as ideias de capa, com 8 quadros;
3. ``matriz``: a descrição das cenas de uma biblioteca;
4. ``avatar``: as partes do avatar pela foto;
5. ``tema``: o roteiro pelo tema;
6. ``buscas``: as buscas das fotos de um roteiro;
7. ``duracao``: as frases que ficam num vídeo cortado para 45 s;
8. ``pesquisa``: o roteiro de uma notícia da semana, com a pesquisa na internet como
   ferramenta da IA (:mod:`editor.pesquisa`). A primeira busca é do Editai; depois, a IA
   busca e lê o que quiser, e o roteiro sai só com o que as fontes trazem.

**As entradas** vêm de um JSON fora do repositório (os vídeos e as fotos de quem roda):

.. code-block:: json

    {"falas": [{"nome": "apresentacao", "plano": "video-editado.plano.json",
                "video": "video-original.mp4"}],
     "biblioteca": "pasta/da/biblioteca",
     "fotos": ["rosto.jpg"],
     "temas": ["Por que o céu é azul"],
     "roteiros": ["roteiro.txt"],
     "cortes": [{"nome": "narracao", "plano": "narrado.plano.json", "segundos": 45}]}

**Rodar** (o modelo vem do cache do Hugging Face, num commit fixo):

.. code-block:: bash

    uv run python ferramentas/comparar_ia.py --entradas e.json --saida prova --ia gemini
    uv run python ferramentas/comparar_ia.py --entradas e.json --saida prova --ia qwen35 \\
        --llama-server caminho/llama-server [--sem-placa]
"""
from __future__ import annotations

import argparse
import base64
import contextlib
import io
import json
import secrets
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, is_dataclass
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from editor import (
    avatar,
    catalogo,
    cenas,
    cortes,
    duracao,
    escrita,
    fotos,
    ia,
    icones,
    pesquisa,
    roteiro,
)
from editor.transcricao import Palavra

#: Os modelos locais da prova: o repositório, o commit, o modelo e o projetor de imagem.
MODELOS = {
    "qwen35": ("unsloth/Qwen3.5-4B-GGUF", "e87f176479d0855a907a41277aca2f8ee7a09523",
               "Qwen3.5-4B-Q4_K_M.gguf", "mmproj-F16.gguf"),
    "gemma4": ("ggml-org/gemma-4-E2B-it-GGUF", "6938c58e698502037401a5f19f6905f2fb2f7dee",
               "gemma-4-E2B-it-Q4_0.gguf", "mmproj-gemma-4-E2B-it-Q8_0.gguf"),
    "qwen3vl": ("Qwen/Qwen3-VL-4B-Instruct-GGUF", "1cd86afb9a95c410a6038ab3b40d8b578c892266",
                "Qwen3VL-4B-Instruct-Q4_K_M.gguf", "mmproj-Qwen3VL-4B-Instruct-F16.gguf"),
    "gemma4e4b": ("ggml-org/gemma-4-E4B-it-GGUF", "a69f018d7678a2b9f5e705f8903d6fb29b9b25dc",
                  "gemma-4-E4B-it-Q4_0.gguf", "mmproj-gemma-4-E4B-it-Q8_0.gguf"),
}
CONTEXTO = 16384
TOKENS_DE_SAIDA = 4096


# ── o modelo local ───────────────────────────────────────────────────────


class Local:
    """O ``llama-server`` de pé, com o modelo, numa porta livre e com uma chave sorteada."""

    def __init__(self, servidor: Path, nome: str, *, placa: bool, registro: Path):
        from huggingface_hub import hf_hub_download

        repo, revisao, modelo, projetor = MODELOS[nome]
        caminho = Path(hf_hub_download(repo, modelo, revision=revisao))
        mmproj = Path(hf_hub_download(repo, projetor, revision=revisao))
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.porta = s.getsockname()[1]
        self.chave = secrets.token_urlsafe(16)
        self.nome = nome
        comando = [str(servidor), "-m", str(caminho), "--mmproj", str(mmproj),
                   "--host", "127.0.0.1", "--port", str(self.porta), "--api-key", self.chave,
                   "-c", str(CONTEXTO), "-ngl", "99" if placa else "0"]
        if not placa:
            comando.append("--no-mmproj-offload")
        comeco = time.monotonic()
        self.processo = subprocess.Popen(comando, stdout=subprocess.DEVNULL,
                                         stderr=registro.open("w"))
        self.base = f"http://127.0.0.1:{self.porta}"
        while True:
            try:
                if httpx.get(self.base + "/health", timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            if self.processo.poll() is not None:
                raise SystemExit(f"o llama-server caiu; veja {registro}")
            time.sleep(0.3)
        self.subiu_em = round(time.monotonic() - comeco, 1)
        self.pico_mb = 0
        self._medindo = True
        threading.Thread(target=self._medir, daemon=True).start()

    def _medir(self) -> None:
        while self._medindo and self.processo.poll() is None:
            try:
                rss = int(subprocess.check_output(["ps", "-o", "rss=", "-p",
                                                   str(self.processo.pid)]))
                self.pico_mb = max(self.pico_mb, rss // 1024)
            except (subprocess.CalledProcessError, ValueError):
                pass
            time.sleep(0.5)

    def perguntar(self, sistema: str, pedido: str, imagens, esquema: dict,
                  temperatura: float) -> tuple[str, dict]:
        conteudo = [{"type": "image_url", "image_url": {
            "url": "data:image/jpeg;base64," + base64.b64encode(b).decode("ascii")}}
            for b in imagens]
        conteudo.append({"type": "text", "text": pedido})
        corpo = {"messages": [{"role": "system", "content": sistema},
                              {"role": "user", "content": conteudo}],
                 "temperature": temperatura, "max_tokens": TOKENS_DE_SAIDA,
                 "chat_template_kwargs": {"enable_thinking": False},
                 "response_format": {"type": "json_schema", "json_schema": {
                     "name": "resposta", "schema": esquema, "strict": True}}}
        r = httpx.post(self.base + "/v1/chat/completions", json=corpo, timeout=900,
                       headers={"Authorization": "Bearer " + self.chave})
        if r.status_code >= 400:
            raise ia.ErroDaIA(f"o llama-server respondeu {r.status_code}: {r.text[:300]}")
        dados = r.json()
        t = dados.get("timings") or {}
        info = {"tokens_de_entrada": t.get("prompt_n"),
                "leitura_s": round((t.get("prompt_ms") or 0) / 1000, 1),
                "tokens_de_saida": t.get("predicted_n"),
                "tokens_por_s": round(t.get("predicted_per_second") or 0, 1)}
        return dados["choices"][0]["message"]["content"], info

    def fechar(self) -> None:
        self._medindo = False
        self.processo.terminate()
        try:
            self.processo.wait(15)
        except subprocess.TimeoutExpired:
            self.processo.kill()


# ── a porta de saída trocada ─────────────────────────────────────────────

#: Cada pedido feito durante a tarefa que está rodando.
CHAMADAS: list[dict] = []


def ligar_local(local: Local) -> None:
    """Todo pedido do editor vai para o modelo local."""
    def perguntar(chave_, sistema, pedido, imagens, esquema, *, temperatura, transporte=None,
                  gasto=None, modelos=()):
        if gasto is not None:
            gasto.append(local.nome)
        comeco = time.monotonic()
        try:
            texto, info = local.perguntar(sistema, pedido, list(imagens), esquema, temperatura)
        except httpx.HTTPError as erro:
            CHAMADAS.append({"segundos": round(time.monotonic() - comeco, 1),
                             "erro": str(erro)})
            raise ia.ErroDaIA(f"o modelo local não respondeu: {erro}") from erro
        chamada = {"segundos": round(time.monotonic() - comeco, 1), "imagens": len(imagens),
                   **info}
        try:
            resposta = json.loads(texto)
        except ValueError:
            CHAMADAS.append({**chamada, "erro": "o JSON veio quebrado"})
            raise ia.ErroDaIA(f"{local.nome}: o JSON veio quebrado") from None
        CHAMADAS.append(chamada)
        return resposta, local.nome

    ia._perguntar = perguntar
    ia.chave = lambda: ("prova-local", "prova")


def medir_o_gemini() -> None:
    """Os pedidos ao Gemini de verdade (a chave salva e a cota grátis), com o tempo de cada
    um."""
    original = ia._perguntar

    def perguntar(*a, **k):
        gasto: list[str] = k.pop("gasto", None) or []
        comeco = time.monotonic()
        antes = len(gasto)
        try:
            resposta, modelo = original(*a, gasto=gasto, **k)
        except ia.ErroDaIA as erro:
            CHAMADAS.append({"segundos": round(time.monotonic() - comeco, 1),
                             "modelos": gasto[antes:], "erro": str(erro)})
            raise
        CHAMADAS.append({"segundos": round(time.monotonic() - comeco, 1), "modelo": modelo,
                         "modelos": gasto[antes:], "imagens": len(a[3])})
        return resposta, modelo

    ia._perguntar = perguntar


# ── as entradas ──────────────────────────────────────────────────────────


def palavras_do_plano(caminho: Path) -> tuple[list[Palavra], float]:
    plano = json.loads(caminho.read_text(encoding="utf-8"))
    palavras = [Palavra(w["texto"], w["inicio"], w["fim"], w.get("prob", 1.0))
                for b in plano["blocos"] for w in b["palavras"]]
    return palavras, float(plano["duracao"])


def quadros_do_video(caminho: Path, n: int = ia.QUADROS
                     ) -> tuple[list[tuple[float, bytes]], float, bool]:
    """``n`` quadros espalhados pelo vídeo, no lado de ``ia.LADO_DO_QUADRO``, como a página
    manda para as ideias de thumbnail."""
    import av

    with av.open(str(caminho)) as c:
        s = c.streams.video[0]
        dur = float(s.duration * s.time_base) if s.duration else float(c.duration / 1e6)
        largura, altura = s.codec_context.width, s.codec_context.height
        saida = []
        for k in range(n):
            t = dur * (k + 0.5) / n
            c.seek(int(t / s.time_base), stream=s)
            for f in c.decode(s):
                if f.time is not None and f.time >= t - 0.05:
                    img = f.to_image().convert("RGB")
                    img.thumbnail((ia.LADO_DO_QUADRO, ia.LADO_DO_QUADRO))
                    buf = io.BytesIO()
                    img.save(buf, "JPEG", quality=85)
                    saida.append((round(t, 2), buf.getvalue()))
                    break
    return saida, dur, altura > largura


# ── as tarefas ───────────────────────────────────────────────────────────


def _json(x):
    if is_dataclass(x):
        return asdict(x)
    if hasattr(x, "para_json"):
        return x.para_json()
    return x


def tarefa_roteiro(fala: dict, biblioteca: cenas.Biblioteca) -> dict:
    palavras, dur = palavras_do_plano(Path(fala["plano"]))
    r = roteiro.escrever(palavras, dur, biblioteca=biblioteca, cartoes=True, idioma="pt",
                         nomes_de_icones=icones.nomes())
    return {"por": r.por, "aviso": r.aviso, "pedidos": r.pedidos,
            "ok": r.por not in ("palavras", ""), "cenas": sum(len(e) for e in r.escolhas),
            "cartoes": len(r.cartoes), "resposta": r.para_json()}


def tarefa_thumbnail(fala: dict) -> dict:
    palavras, _ = palavras_do_plano(Path(fala["plano"]))
    quadros, dur, em_pe = quadros_do_video(Path(fala["video"]))
    r = ia.sugerir(" ".join(w.texto for w in palavras), quadros, idioma="pt", duracao=dur,
                   vertical=em_pe, nomes_de_icones=icones.nomes())
    return {"ok": bool(r["variantes"]), "pedidos": r["pedidos"],
            "ideias": len(r["variantes"]), "resposta": r["variantes"]}


def tarefa_matriz(pasta: Path) -> dict:
    catalogo._ler_guardadas = lambda: {}          # sem as descrições guardadas
    catalogo._guardar = lambda guardadas: None
    g = catalogo.gerar(catalogo.clipes_relativos(pasta))
    descritas = sum(1 for c in g.cenas if c.get("obs") != "descreva esta cena")
    return {"ok": not g.aviso, "aviso": g.aviso, "pedidos": g.pedidos,
            "descritas": descritas, "total": len(g.cenas), "resposta": g.cenas}


def tarefa_avatar(foto: Path) -> dict:
    r = avatar.escolher_partes(foto.read_bytes())
    return {"ok": True, "resposta": r}


def tarefa_tema(tema: str, segundos: float | None) -> dict:
    r = escrita.escrever(tema, segundos, teto=180)
    resposta = {"titulo": r.titulo, "paragrafos": r.paragrafos}
    problemas = escrita.conferir(resposta, segundos, teto=180)[1]
    return {"ok": not problemas, "pedidos": r.pedidos, "palavras": r.palavras,
            "alvo": escrita.palavras_alvo(segundos) if segundos else None,
            "problemas": problemas, "resposta": resposta}


def tarefa_buscas(caminho: Path) -> dict:
    trechos = fotos.blocos(caminho.read_text(encoding="utf-8"))
    lista, pedidos = fotos.buscas(trechos, caminho.parent.name.replace("-", " "))
    pela_ia = sum(1 for b in lista if b.alvo != b.termo)
    return {"ok": pela_ia == len(lista), "pedidos": pedidos, "trechos": len(lista),
            "pela_ia": pela_ia, "resposta": [_json(b) for b in lista]}


def tarefa_duracao(fala: dict, segundos: float) -> dict:
    palavras, dur = palavras_do_plano(Path(fala["plano"]))
    linha = cortes.Linha([cortes.Trecho(0.0, dur)])
    s = duracao.escolher(palavras, linha, dur, escolha=segundos)
    return {"ok": s.por == "gemini", "pedidos": s.pedidos,
            "antes": round(s.antes, 1), "depois": round(s.depois, 1), "aviso": s.aviso,
            "resposta": s.para_json()}


# ── a pesquisa (a tarefa 8) ──────────────────────────────────────────────

#: Quantas voltas de ferramenta a IA pode dar antes de ter de responder.
VOLTAS = 6


def _sistema_da_pesquisa() -> str:
    hoje = time.strftime("%d/%m/%Y")
    return f"""Você pesquisa os fatos de um roteiro de vídeo curto. Hoje é {hoje}.
O que você sabe tem data de corte e pode estar velho: o que as fontes trazem é real, mesmo que
você não conheça o assunto. Use as ferramentas quando precisar de mais (no máximo 4 buscas e 3
leituras). Quando tiver o bastante, sem chamar ferramenta, responda com as notas: os fatos que
o roteiro pode usar, um por linha, cada um com o número da fonte entre colchetes, como [3]."""


def _pedido_inicial(tema: str, p: pesquisa.Pesquisa) -> str:
    """O tema e a primeira busca, que é do Editai e não da IA: o modelo não sabe o que não
    sabe, e acha que conhece o assunto."""
    achadas = []
    for tipo in ("noticias", "fatos"):
        with contextlib.suppress(pesquisa.SemPesquisa):
            achadas += p.pesquisar(tema, tipo)
    resultados = json.dumps([{"n": a.numero, "titulo": a.titulo, "trecho": a.trecho,
                              "fonte": a.fonte, "data": a.data, "link": a.link}
                             for a in achadas], ensure_ascii=False)
    return f"O tema do vídeo: {tema}\n\nA primeira busca achou:\n{resultados}"


def notas_local(local: Local, tema: str, p: pesquisa.Pesquisa) -> str:
    mensagens = [{"role": "system", "content": _sistema_da_pesquisa()},
                 {"role": "user", "content": _pedido_inicial(tema, p)}]
    for volta in range(VOLTAS + 1):
        corpo = {"messages": mensagens, "temperature": 0.3, "max_tokens": 2000,
                 "chat_template_kwargs": {"enable_thinking": False}}
        if volta < VOLTAS:
            corpo["tools"] = pesquisa.FERRAMENTAS
        comeco = time.monotonic()
        r = httpx.post(local.base + "/v1/chat/completions", json=corpo, timeout=900,
                       headers={"Authorization": "Bearer " + local.chave})
        if r.status_code >= 400:
            raise ia.ErroDaIA(f"o llama-server respondeu {r.status_code}: {r.text[:300]}")
        msg = r.json()["choices"][0]["message"]
        chamadas = msg.get("tool_calls") or []
        CHAMADAS.append({"segundos": round(time.monotonic() - comeco, 1),
                         "ferramentas": [c["function"]["name"] for c in chamadas]})
        if not chamadas:
            return msg.get("content") or ""
        mensagens.append({"role": "assistant", "content": msg.get("content") or "",
                          "tool_calls": chamadas})
        for c in chamadas:
            try:
                argumentos = json.loads(c["function"].get("arguments") or "{}")
            except ValueError:
                argumentos = {}
            mensagens.append({"role": "tool", "tool_call_id": c.get("id") or "",
                              "content": p.executar(c["function"]["name"], argumentos)})
    return ""


def notas_gemini(tema: str, p: pesquisa.Pesquisa) -> str:
    chave_ = ia.chave()[0]
    declaracoes = [f["function"] for f in pesquisa.FERRAMENTAS]
    conteudos = [{"role": "user", "parts": [{"text": _pedido_inicial(tema, p)}]}]
    for volta in range(VOLTAS + 1):
        corpo = {"systemInstruction": {"parts": [{"text": _sistema_da_pesquisa()}]},
                 "contents": conteudos, "generationConfig": {"temperature": 0.3}}
        if volta < VOLTAS:
            corpo["tools"] = [{"functionDeclarations": declaracoes}]
        dados, modelo = None, ""
        for modelo in ia.MODELOS:
            comeco = time.monotonic()
            r = httpx.post(f"{ia.API}/models/{modelo}:generateContent", json=corpo,
                           headers={"x-goog-api-key": chave_}, timeout=300)
            if r.status_code == 200:
                dados = r.json()
                break
            CHAMADAS.append({"segundos": round(time.monotonic() - comeco, 1),
                             "modelo": modelo, "erro": f"{r.status_code} {r.text[:200]}"})
        if dados is None:
            raise ia.ErroDaIA("o Gemini não respondeu à pesquisa")
        conteudo = dados["candidates"][0]["content"]
        chamadas = [x["functionCall"] for x in conteudo.get("parts", []) if "functionCall" in x]
        CHAMADAS.append({"segundos": round(time.monotonic() - comeco, 1), "modelo": modelo,
                         "ferramentas": [c["name"] for c in chamadas]})
        if not chamadas:
            return "".join(x.get("text", "") for x in conteudo.get("parts", [])
                           if not x.get("thought"))
        conteudos.append(conteudo)          # com a assinatura do raciocínio, que o 3.x pede
        conteudos.append({"role": "user", "parts": [
            {"functionResponse": {"name": c["name"], "response": {
                "resultado": p.executar(c["name"], c.get("args") or {})}}} for c in chamadas]})
    return ""


#: Quem pesquisa nesta rodada (o modelo local ou o Gemini): definido no ``main``.
ANOTAR: Callable[[str, pesquisa.Pesquisa], str] = notas_gemini


def tarefa_pesquisa(tema: str) -> dict:
    p = pesquisa.Pesquisa()
    notas = ANOTAR(tema, p)
    pedido = (escrita.montar_pedido(tema, None, teto=180)
              + f"\n\nHOJE É {time.strftime('%d/%m/%Y')}. Os fatos que a pesquisa achou (são "
              "reais, mesmo os que você não conhece; use só estes números, datas e nomes, e o "
              f"que não estiver aqui não afirme):\n{notas}\n\nAs fontes:\n{p.para_o_pedido()}")
    resposta, _modelo = ia._perguntar(ia.chave()[0], escrita.SISTEMA, pedido, [],
                                      escrita.esquema(), temperatura=0.8)
    r, problemas = escrita.conferir(resposta, None, teto=180)
    return {"ok": bool(notas.strip()) and not problemas, "buscas_da_ia": len(p.feitas) - 2,
            "notas": notas, "pesquisa": p.para_json(), "problemas": problemas,
            "palavras": r.palavras, "resposta": {"titulo": r.titulo, "paragrafos": r.paragrafos}}


def tarefas(entradas: dict) -> list[tuple[str, Callable[[], dict]]]:
    pasta = Path(entradas["biblioteca"])
    biblioteca = cenas.ler_matriz((pasta / "cenas.json").read_text(encoding="utf-8"),
                                  cenas.clipes_da_pasta(pasta))
    lista: list[tuple[str, Callable[[], dict]]] = []
    for f in entradas["falas"]:
        lista.append((f"roteiro-{f['nome']}", lambda f=f: tarefa_roteiro(f, biblioteca)))
    for f in entradas["falas"]:
        if f.get("video"):
            lista.append((f"thumbnail-{f['nome']}", lambda f=f: tarefa_thumbnail(f)))
    lista.append(("matriz", lambda: tarefa_matriz(pasta)))
    for k, foto in enumerate(entradas["fotos"]):
        lista.append((f"avatar-{k + 1}", lambda foto=foto: tarefa_avatar(Path(foto))))
    for k, tema in enumerate(entradas["temas"]):
        lista.append((f"tema-{k + 1}-45s", lambda tema=tema: tarefa_tema(tema, 45)))
        lista.append((f"tema-{k + 1}-auto", lambda tema=tema: tarefa_tema(tema, None)))
    for k, caminho in enumerate(entradas["roteiros"]):
        lista.append((f"buscas-{k + 1}", lambda c=caminho: tarefa_buscas(Path(c))))
    for c in entradas.get("cortes", []):
        lista.append((f"duracao-{c['nome']}",
                      lambda c=c: tarefa_duracao(c, float(c["segundos"]))))
    for k, tema in enumerate(entradas.get("noticias", [])):
        lista.append((f"pesquisa-{k + 1}", lambda tema=tema: tarefa_pesquisa(tema)))
    return lista


# ── rodar ────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--entradas", type=Path, required=True)
    p.add_argument("--saida", type=Path, required=True)
    p.add_argument("--ia", required=True, help="gemini, ou um dos modelos: " + ", ".join(MODELOS))
    p.add_argument("--llama-server", type=Path)
    p.add_argument("--sem-placa", action="store_true", help="o modelo só no processador")
    p.add_argument("--so", default="", help="só as tarefas que começam assim (vírgulas)")
    p.add_argument("--lote-da-matriz", type=int, default=0,
                   help=f"quantas cenas por pedido na matriz (o editor usa {catalogo.POR_PEDIDO})")
    a = p.parse_args(argv)
    entradas = json.loads(a.entradas.read_text(encoding="utf-8"))
    nome = (a.ia + ("-sem-placa" if a.sem_placa else "")
            + (f"-lote{a.lote_da_matriz}" if a.lote_da_matriz else ""))
    if a.lote_da_matriz:
        catalogo.POR_PEDIDO = a.lote_da_matriz
    pasta = a.saida / nome
    pasta.mkdir(parents=True, exist_ok=True)
    local = None
    if a.ia == "gemini":
        medir_o_gemini()
    else:
        if a.ia not in MODELOS or not a.llama_server:
            p.error("um modelo local pede --llama-server e um nome de " + ", ".join(MODELOS))
        local = Local(a.llama_server, a.ia, placa=not a.sem_placa,
                      registro=pasta / "llama-server.log")
        ligar_local(local)
        global ANOTAR
        ANOTAR = lambda tema, p: notas_local(local, tema, p)  # noqa: E731
        print(f"{nome}: o servidor subiu em {local.subiu_em} s", flush=True)
    filtro = [x for x in a.so.split(",") if x]
    resumo = []
    try:
        for tarefa, rodar in tarefas(entradas):
            if filtro and not any(tarefa.startswith(x) for x in filtro):
                continue
            CHAMADAS.clear()
            if local:
                local.pico_mb = 0
            comeco = time.monotonic()
            try:
                r = rodar()
            except Exception as erro:          # a tarefa que caiu entra no resumo assim
                r = {"ok": False, "erro": f"{type(erro).__name__}: {erro}"}
            r = {"tarefa": tarefa, "ia": nome, "segundos": round(time.monotonic() - comeco, 1),
                 "chamadas": list(CHAMADAS), **r}
            if local:
                r["memoria_mb"] = local.pico_mb
            (pasta / f"{tarefa}.json").write_text(
                json.dumps(r, ensure_ascii=False, indent=1, default=_json), encoding="utf-8")
            resumo.append({k: v for k, v in r.items() if k not in ("resposta", "chamadas")})
            print(f"  {tarefa:28s} {'ok ' if r.get('ok') else 'NÃO'} {r['segundos']:6.1f} s "
                  f"{len(r['chamadas'])} pedido(s) {r.get('erro', '')}", flush=True)
    finally:
        if local:
            local.fechar()
    (pasta / "resumo.json").write_text(json.dumps(
        {"ia": nome, "subiu_em": local.subiu_em if local else None, "tarefas": resumo},
        ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
