"""
A IA local: o Qwen3.5-4B, pelo ``llama-server`` do llama.cpp, no computador de quem usa. Ela
faz as tarefas de texto e de imagem (o roteiro, as ideias de capa, a matriz, o avatar…) sem
internet e sem chave, e nada sai do computador.

**A instalação** (o botão da página, ou ``editai --instalar-ia``):

1. **o programa:** o ``llama-server`` do release fixado do llama.cpp (``b11669``, a v0.7.0, de
   15/10/2026), conferido pelo SHA-256. No Windows e no Linux vai o pacote com Vulkan (a placa
   de vídeo de qualquer marca) e, se ele não abrir, o só de processador;
2. **o modelo** (2,7 GB) e o projetor de imagem (0,7 GB), do Hugging Face num commit fixo,
   conferidos pelo SHA-256;
3. **um pedido de teste.**

Uns 3,5 GB no total, numa pasta só (``<dados>/ia-local``), que o desinstalador apaga inteira.

**O uso:** o servidor sobe no primeiro pedido, em ``127.0.0.1``, numa porta livre e com uma
chave sorteada a cada vez. Ele fica de pé por ``OCIOSO_S`` depois do último pedido, para o
seguinte não esperar, e cai ao fechar o editor.

**A escolha do modelo** saiu da prova de 26/10/2026 (``ferramentas/comparar_ia.py``), num
MacBook M5:

- **os candidatos:** o Qwen3.5-4B, o Gemma 4 E2B e E4B e o Qwen3-VL-4B, nas tarefas do
  editor;
- **por que o Qwen3.5-4B:** ele descreveu certo 18 de 19 fotos de um imóvel (o Gemma E4B, 12)
  e ocupa 5,5 GB de memória (o E4B, 7,2 GB). Gerou 31 tokens por segundo na placa e 16 só no
  processador;
- **o limite:** no texto, ele fica atrás do Gemini. Os roteiros saem mais longos e erram mais
  fatos.
"""
from __future__ import annotations

import atexit
import base64
import contextlib
import hashlib
import json
import logging
import platform
import secrets
import shutil
import socket
import subprocess
import sys
import tarfile
import threading
import time
import zipfile
from collections.abc import Sequence
from pathlib import Path

logger = logging.getLogger(__name__)

#: O release do llama.cpp e os pacotes de cada sistema, com o SHA-256 (lidos em 26/10/2026).
VERSAO_DO_LLAMA = "b11669"
PACOTES = {
    ("darwin", "arm64"): [("llama-b11669-bin-macos-arm64.tar.gz",
                           "dbed55493d72bc1ba2babc8770d669c2289b5bc4ee9fb2a4dfc158d45b7d13fd")],
    ("darwin", "x64"): [("llama-b11669-bin-macos-x64.tar.gz",
                         "cab28238d78158109b48deb27b05d50e0dcef56275d2e76da9ca8281526c7532")],
    ("win32", "x64"): [("llama-b11669-bin-win-vulkan-x64.zip",
                        "2c07574e7bde71321cb785282b20cc821e951132149eeceeea32ddebdbf0598e"),
                       ("llama-b11669-bin-win-cpu-x64.zip",
                        "37b3efcf962847ca869745fd4ccf7f5e7e8dacfeff9fa3523b4ca8cdc66d632b")],
    ("win32", "arm64"): [("llama-b11669-bin-win-vulkan-arm64.zip",
                          "963d3b185362cadca3de643409f916a5ce95dd0f7fd8617ba9ee5d8833ac1ef3"),
                         ("llama-b11669-bin-win-cpu-arm64.zip",
                          "9cff39ffed17edcd03a7d876073f74d7b48cd43a1e5eafdd59ee094185ad871b")],
    ("linux", "x64"): [("llama-b11669-bin-ubuntu-vulkan-x64.tar.gz",
                        "e8709e5ba6c1b093dea7f3de57f4aba842f9a188fba6b465782d65d6fcfa4d9f"),
                       ("llama-b11669-bin-ubuntu-x64.tar.gz",
                        "cf07c1c112d709bd67e522017471de57ed0ec8bea031d732c5422351c07f65ac")],
    ("linux", "arm64"): [("llama-b11669-bin-ubuntu-vulkan-arm64.tar.gz",
                          "d283522e479c0d532e3a04d715dd852ffb2d95925caa6d41ef2ba53a65e46a51"),
                         ("llama-b11669-bin-ubuntu-arm64.tar.gz",
                          "9ac6fda2058d35677608a06f751a50122ddfa4ce0ddb7f084466b8e79b6d4a99")],
}
RELEASES = "https://github.com/ggml-org/llama.cpp/releases/download"
#: O modelo, num commit fixo do Hugging Face, e o SHA-256 de cada arquivo.
REPO = "unsloth/Qwen3.5-4B-GGUF"
REVISAO = "e87f176479d0855a907a41277aca2f8ee7a09523"
MODELO = "Qwen3.5-4B-Q4_K_M.gguf"
PROJETOR = "mmproj-F16.gguf"
ARQUIVOS = {MODELO: "00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4",
            PROJETOR: "cd88edcf8d031894960bb0c9c5b9b7e1fea6ebee02b9f7ce925a00d12891f864"}
NOME = "Qwen3.5-4B"
ESPACO = "uns 3,5 GB"
TEMPO = "de 3 a 10 minutos, conforme a internet"

#: O contexto (o pedido e a resposta, em tokens) e o tamanho máximo da resposta.
CONTEXTO = 16384
TOKENS_DE_SAIDA = 4096
#: Quanto tempo o servidor fica de pé depois do último pedido.
OCIOSO_S = 300.0
#: Quanto esperar o servidor subir e cada resposta (a leitura de 8 imagens, sem placa, passa
#: de um minuto).
SUBIDA_S = 120.0
RESPOSTA_S = 900.0

ETAPAS = {"programa": ("Baixando o programa (de 12 a 32 MB)", 0.0, 0.03),
          "modelo": ("Baixando o modelo (3,4 GB)", 0.03, 0.95),
          "teste": ("Testando a IA", 0.95, 1.0)}


class ErroDaIALocal(RuntimeError):
    """A instalação ou o pedido falharam (a mensagem diz o que fazer)."""


def pasta() -> Path:
    from editor.ia import pasta_de_dados

    return pasta_de_dados() / "ia-local"


def _marca() -> Path:
    return pasta() / "instalado.json"


def _registro() -> dict:
    try:
        return json.loads(_marca().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def sistema() -> tuple[str, str]:
    """O sistema e a arquitetura, nos nomes de ``PACOTES``."""
    nome = "win32" if sys.platform == "win32" else sys.platform
    if nome not in ("darwin", "win32"):
        nome = "linux"
    maquina = platform.machine().lower()
    arquitetura = "arm64" if maquina in ("arm64", "aarch64") else "x64"
    return nome, arquitetura


def servidor() -> Path | None:
    """O ``llama-server`` instalado (o pacote que passou no teste)."""
    pacote = _registro().get("pacote")
    if not pacote:
        return None
    nome = "llama-server.exe" if sys.platform == "win32" else "llama-server"
    achados = sorted((pasta() / "programa" / pacote).rglob(nome))
    return achados[0] if achados else None


def instalado() -> bool:
    return (_marca().is_file() and servidor() is not None
            and all((pasta() / "modelo" / n).is_file() for n in ARQUIVOS))


# ── a instalação ─────────────────────────────────────────────────────────


class _Instalacao:
    def __init__(self) -> None:
        self.rodando = False
        self.etapa = ""
        self.fracao = 0.0
        self.erro = ""
        self.parar = threading.Event()


_instalacao = _Instalacao()
_trava = threading.Lock()


def estado() -> dict:
    from editor import desinstalar

    i = _instalacao
    ocupa = desinstalar.tamanho(pasta()) if instalado() else 0
    return {"instalado": instalado(), "instalando": i.rodando, "modelo": NOME,
            "etapa": ETAPAS.get(i.etapa, (i.etapa,))[0] if i.etapa else "",
            "fracao": round(i.fracao, 3), "erro": i.erro, "espaco": ESPACO, "tempo": TEMPO,
            "ocupa": desinstalar.legivel(ocupa) if ocupa else ""}


def _baixar(url: str, destino: Path, sha: str, *, de: float, ate: float,
            transporte=None) -> None:
    """Baixa ``url`` em ``destino``, conferindo o SHA-256 no caminho; o andamento vai de
    ``de`` a ``ate``. Se a conexão cair, tenta mais uma vez: na primeira instalação de
    verdade, o projetor parou no meio e a segunda tentativa passou."""
    try:
        _baixar_uma_vez(url, destino, sha, de=de, ate=ate, transporte=transporte)
    except _Caiu:
        logger.info("o download de %s caiu; tentando de novo", destino.name)
        try:
            _baixar_uma_vez(url, destino, sha, de=de, ate=ate, transporte=transporte)
        except _Caiu as erro:
            raise ErroDaIALocal("O download parou (a internet caiu?). Tente de novo.") from erro


class _Caiu(ErroDaIALocal):
    """A conexão caiu no meio do download."""


def _baixar_uma_vez(url: str, destino: Path, sha: str, *, de: float, ate: float,
                    transporte=None) -> None:
    """Um download; o arquivo pela metade (cancelado, ou a internet caiu) é apagado."""
    import httpx

    i = _instalacao
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_name(destino.name + ".parcial")
    h = hashlib.sha256()
    try:
        with httpx.Client(transport=transporte, timeout=60.0, follow_redirects=True) as c, \
                c.stream("GET", url) as r:
            if r.status_code >= 400:
                raise ErroDaIALocal(f"O download respondeu {r.status_code} ({url}).")
            total = int(r.headers.get("content-length") or 0)
            feitos = 0
            with parcial.open("wb") as f:
                for bloco in r.iter_bytes(1024 * 1024):
                    if i.parar.is_set():
                        raise ErroDaIALocal("A instalação foi cancelada.")
                    f.write(bloco)
                    h.update(bloco)
                    feitos += len(bloco)
                    if total:
                        i.fracao = de + (ate - de) * feitos / total
    except httpx.HTTPError as erro:
        parcial.unlink(missing_ok=True)
        raise _Caiu(str(erro)) from erro
    except ErroDaIALocal:
        parcial.unlink(missing_ok=True)
        raise
    if h.hexdigest() != sha:
        parcial.unlink(missing_ok=True)
        raise ErroDaIALocal(f"O arquivo baixado não confere ({destino.name}: o SHA-256 é "
                            "outro). Tente de novo.")
    parcial.replace(destino)


def _abrir_o_pacote(arquivo: Path, destino: Path) -> None:
    destino.mkdir(parents=True, exist_ok=True)
    raiz = destino.resolve()
    if arquivo.name.endswith(".zip"):
        with zipfile.ZipFile(arquivo) as z:
            for nome in z.namelist():         # nenhum caminho sai da pasta
                if not (destino / nome).resolve().is_relative_to(raiz):
                    raise ErroDaIALocal("O pacote do programa tem um caminho estranho.")
            z.extractall(destino)
    else:
        with tarfile.open(arquivo) as t:
            t.extractall(destino, filter="data")


def _testar(executavel: Path) -> None:
    """Sobe o servidor com o modelo e faz um pedido curto."""
    s = _Servidor(executavel)
    try:
        resposta = s.perguntar_json("Responda só com o JSON pedido.", "Diga ok.",
                                    {"type": "object", "properties": {"ok": {"type": "string"}},
                                     "required": ["ok"]}, [], 0.0, max_tokens=20)
        if "ok" not in resposta:
            raise ErroDaIALocal("A IA local respondeu, mas fora do formato pedido.")
    finally:
        s.parar()


def _programa(arquivo: str, sha: str, *, transporte=None) -> Path | None:
    """Baixa e abre um pacote do llama.cpp; devolve o ``llama-server`` de dentro dele."""
    pacote = arquivo.removesuffix(".zip").removesuffix(".tar.gz")
    baixado = pasta() / "pacotes" / arquivo
    if not baixado.is_file():
        _baixar(f"{RELEASES}/{VERSAO_DO_LLAMA}/{arquivo}", baixado, sha, de=0.0,
                ate=ETAPAS["programa"][2], transporte=transporte)
    _abrir_o_pacote(baixado, pasta() / "programa" / pacote)
    nome = "llama-server.exe" if sys.platform == "win32" else "llama-server"
    return next(iter(sorted((pasta() / "programa" / pacote).rglob(nome))), None)


def _executar(*, transporte=None) -> dict:
    i = _instalacao
    try:
        pacotes = PACOTES.get(sistema())
        if not pacotes:
            raise ErroDaIALocal(f"Ainda não há a IA local para este sistema ({sistema()}).")
        pasta().mkdir(parents=True, exist_ok=True)
        i.etapa, i.fracao = "programa", 0.0
        primeiro = _programa(*pacotes[0], transporte=transporte)
        i.etapa = "modelo"
        _, de, ate = ETAPAS["modelo"]
        tamanhos = {MODELO: 2.74, PROJETOR: 0.67}
        feito = 0.0
        for nome, sha in ARQUIVOS.items():
            destino = pasta() / "modelo" / nome
            parte = (ate - de) * tamanhos[nome] / sum(tamanhos.values())
            if not destino.is_file():
                _baixar(f"https://huggingface.co/{REPO}/resolve/{REVISAO}/{nome}", destino, sha,
                        de=de + feito, ate=de + feito + parte, transporte=transporte)
            feito += parte
        erros = []
        # o pacote com a placa de vídeo primeiro; se ele não abrir, o só de processador
        for k, (arquivo, sha) in enumerate(pacotes):
            executavel = primeiro if k == 0 else _programa(arquivo, sha, transporte=transporte)
            if executavel is None:
                erros.append(f"{arquivo}: sem o llama-server dentro")
                continue
            i.etapa, i.fracao = "teste", ETAPAS["teste"][1]
            try:
                _testar(executavel)
            except ErroDaIALocal as erro:
                erros.append(f"{arquivo}: {erro}")
                continue
            registro = {"pacote": arquivo.removesuffix(".zip").removesuffix(".tar.gz"),
                        "llama": VERSAO_DO_LLAMA, "repo": REPO, "revisao": REVISAO,
                        "modelo": MODELO, "quando": time.strftime("%Y-%m-%d")}
            _marca().write_text(json.dumps(registro, ensure_ascii=False, indent=1),
                                encoding="utf-8")
            shutil.rmtree(pasta() / "pacotes", ignore_errors=True)
            i.fracao = 1.0
            return registro
        raise ErroDaIALocal("A IA local não abriu neste computador: " + " | ".join(erros))
    except ErroDaIALocal as erro:
        i.erro = str(erro)
        raise
    except Exception as erro:
        i.erro = f"A instalação falhou: {type(erro).__name__}: {erro}"
        raise ErroDaIALocal(i.erro) from erro
    finally:
        i.rodando = False


def _comecar() -> None:
    i = _instalacao
    with _trava:
        if i.rodando:
            raise ErroDaIALocal("A instalação já está rodando.")
        i.rodando, i.erro, i.etapa, i.fracao = True, "", "", 0.0
        i.parar.clear()


def instalar(*, transporte=None) -> dict:
    """Instala a IA local (bloqueia até o fim)."""
    _comecar()
    return _executar(transporte=transporte)


def instalar_em_segundo_plano() -> dict:
    _comecar()

    def rodar() -> None:
        try:
            _executar()
        except ErroDaIALocal:
            logger.exception("a IA local não instalou")

    threading.Thread(target=rodar, daemon=True, name="instalar-a-ia-local").start()
    return estado()


def cancelar_instalacao() -> None:
    _instalacao.parar.set()


def desinstalar() -> None:
    if _instalacao.rodando:
        raise ErroDaIALocal("Espere a instalação terminar (ou cancele) para desinstalar.")
    soltar()
    shutil.rmtree(pasta(), ignore_errors=True)


# ── o servidor ───────────────────────────────────────────────────────────


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _Servidor:
    """Um ``llama-server`` de pé, com o modelo, numa porta livre e com uma chave sorteada."""

    def __init__(self, executavel: Path):
        modelo = pasta() / "modelo"
        self.porta = _porta_livre()
        self.chave = secrets.token_urlsafe(24)
        self.base = f"http://127.0.0.1:{self.porta}"
        self.ultimo = time.monotonic()
        self.registro = pasta() / "servidor.log"
        comando = [str(executavel), "-m", str(modelo / MODELO), "--mmproj",
                   str(modelo / PROJETOR), "--host", "127.0.0.1", "--port", str(self.porta),
                   "--api-key", self.chave, "-c", str(CONTEXTO), "-ngl", "99"]
        with self.registro.open("wb") as saida:
            self.processo = subprocess.Popen(comando, stdout=subprocess.DEVNULL, stderr=saida,
                                             cwd=str(executavel.parent))
        self._esperar()

    def _esperar(self) -> None:
        import httpx

        fim = time.monotonic() + SUBIDA_S
        while time.monotonic() < fim:
            if self.processo.poll() is not None:
                raise ErroDaIALocal("A IA local fechou ao abrir: " + self._fim_do_registro())
            with contextlib.suppress(httpx.HTTPError):
                if httpx.get(self.base + "/health", timeout=2).status_code == 200:
                    return
            time.sleep(0.3)
        self.parar()
        raise ErroDaIALocal("A IA local demorou demais para abrir.")

    def _fim_do_registro(self) -> str:
        try:
            linhas = self.registro.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return "sem mensagem"
        return " | ".join(linha.strip() for linha in linhas[-3:]) or "sem mensagem"

    def vivo(self) -> bool:
        return self.processo.poll() is None

    def pedir(self, corpo: dict) -> dict:
        import httpx

        self.ultimo = time.monotonic()
        try:
            r = httpx.post(self.base + "/v1/chat/completions", json=corpo, timeout=RESPOSTA_S,
                           headers={"Authorization": "Bearer " + self.chave})
        except httpx.HTTPError as erro:
            raise ErroDaIALocal(f"A IA local não respondeu: {erro}") from erro
        finally:
            self.ultimo = time.monotonic()
        if r.status_code >= 400:
            raise ErroDaIALocal(f"A IA local respondeu {r.status_code}: {r.text[:300]}")
        return r.json()

    def perguntar_json(self, sistema_: str, pedido: str, esquema: dict,
                       imagens: Sequence[bytes], temperatura: float, *,
                       max_tokens: int = TOKENS_DE_SAIDA) -> dict:
        dados = self.pedir(corpo_json(sistema_, pedido, esquema, imagens, temperatura,
                                      max_tokens=max_tokens))
        escolha = dados["choices"][0]
        if escolha.get("finish_reason") == "length":
            raise ErroDaIALocal("A resposta da IA local foi cortada por falta de espaço.")
        try:
            return json.loads(escolha["message"]["content"])
        except (ValueError, TypeError) as erro:
            raise ErroDaIALocal("A IA local respondeu um JSON quebrado.") from erro

    def parar(self) -> None:
        if self.processo.poll() is None:
            self.processo.terminate()
            try:
                self.processo.wait(15)
            except subprocess.TimeoutExpired:
                self.processo.kill()


def corpo_json(sistema_: str, pedido: str, esquema: dict, imagens: Sequence[bytes],
               temperatura: float, *, max_tokens: int = TOKENS_DE_SAIDA) -> dict:
    """O pedido no formato OpenAI do ``llama-server``: as imagens antes do texto (a pergunta
    feita depois das provas é sobre as provas), o JSON preso ao esquema e sem o modo de
    pensar (o Qwen3.5 pensa por padrão, e a resposta levaria minutos a mais)."""
    conteudo: list[dict] = [{"type": "image_url", "image_url": {
        "url": "data:image/jpeg;base64," + base64.b64encode(b).decode("ascii")}}
        for b in imagens]
    conteudo.append({"type": "text", "text": pedido})
    return {"messages": [{"role": "system", "content": sistema_},
                         {"role": "user", "content": conteudo}],
            "temperature": temperatura, "max_tokens": max_tokens,
            "chat_template_kwargs": {"enable_thinking": False},
            "response_format": {"type": "json_schema", "json_schema": {
                "name": "resposta", "schema": esquema, "strict": True}}}


_aberto: _Servidor | None = None
_trava_do_servidor = threading.Lock()


def _vigiar() -> None:
    """Fecha o servidor parado há mais de ``OCIOSO_S``: a memória volta toda."""
    global _aberto
    while True:
        time.sleep(15)
        with _trava_do_servidor:
            if _aberto is None:
                return
            if not _aberto.vivo() or time.monotonic() - _aberto.ultimo > OCIOSO_S:
                _aberto.parar()
                _aberto = None
                return


def _servidor() -> _Servidor:
    global _aberto
    with _trava_do_servidor:
        if _aberto is not None and _aberto.vivo():
            _aberto.ultimo = time.monotonic()
            return _aberto
        executavel = servidor()
        if executavel is None or not instalado():
            raise ErroDaIALocal("A IA local não está instalada: instale em \"A IA\", em Antes "
                                "de começar, ou com editai --instalar-ia.")
        _aberto = _Servidor(executavel)
        threading.Thread(target=_vigiar, daemon=True, name="ia-local-ociosa").start()
        return _aberto


def perguntar_json(sistema_: str, pedido: str, esquema: dict, *, temperatura: float,
                   imagens: Sequence[bytes] = ()) -> dict:
    """O JSON da resposta da IA local, subindo o servidor se preciso."""
    return _servidor().perguntar_json(sistema_, pedido, esquema, list(imagens), temperatura)


def conversar(mensagens: list[dict], *, ferramentas: Sequence[dict] = (),
              temperatura: float = 0.3, max_tokens: int = 2000) -> dict:
    """Uma volta de conversa, com as ferramentas que a IA pode pedir (no formato da OpenAI).
    Devolve a mensagem dela: o texto em ``content`` e os pedidos em ``tool_calls``."""
    corpo: dict = {"messages": mensagens, "temperature": temperatura, "max_tokens": max_tokens,
                   "chat_template_kwargs": {"enable_thinking": False}}
    if ferramentas:
        corpo["tools"] = list(ferramentas)
    return _servidor().pedir(corpo)["choices"][0]["message"]


def soltar() -> None:
    """Fecha o servidor agora (ao fechar o editor, ou ao desinstalar)."""
    global _aberto
    with _trava_do_servidor:
        if _aberto is not None:
            _aberto.parar()
            _aberto = None


atexit.register(soltar)


__all__ = ["ARQUIVOS", "ESPACO", "MODELO", "NOME", "PACOTES", "REPO", "REVISAO", "TEMPO",
           "ErroDaIALocal", "cancelar_instalacao", "conversar", "corpo_json", "desinstalar",
           "estado",
           "instalado", "instalar", "instalar_em_segundo_plano", "pasta", "perguntar_json",
           "servidor", "sistema", "soltar"]
