"""
As vozes prontas: quem narra o roteiro quando a pessoa não grava a própria voz (no vídeo só
pelo tema, por exemplo).

- **Gemini** (``gemini-2.5-flash-preview-tts``):
  - **a cota grátis** é de **10 narrações por dia** (a linha do console diz "100 -90": o grátis
    tem 90 a menos que o pago), por isso **a narração inteira vai num pedido só**, e a mesma
    narração pedida de novo sai do cache, sem gastar;
  - **a direção de locução** vai na frente do texto, sempre a mesma: mandando só o texto, o
    modelo decidia a entrega a cada pedido, e o apresentador "mudava de voz" no meio do vídeo.
- **Local** (:mod:`editor.voz_local`): o Piper, sem internet e sem cota, frase a frase, com o
  mesmo cache e as mesmas pausas da Minha voz.

As duas entregam o WAV no formato da Minha voz (:func:`voz_clonada.narrar`): nivelado, com o
roteiro ao lado. Dali em diante é a narração de sempre: vira um áudio separado, e dela saem a
legenda e os cortes.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from editor import ia, voz, voz_clonada, voz_local
from editor import video as video_mod

logger = logging.getLogger(__name__)

MODELO_TTS = "gemini-2.5-flash-preview-tts"
#: As narrações por dia na chave grátis (conferido no console do Google).
POR_DIA = 10
#: O PCM que o Gemini devolve: 16 bits, mono, 24 kHz.
TAXA_DO_GEMINI = 24_000
#: Quantas letras vão num pedido só. Um roteiro maior é partido nos parágrafos (cada parte
#: gasta uma narração da cota).
LETRAS_POR_PEDIDO = 4000
#: A direção de locução, sempre a mesma (ver o topo do módulo).
DIRECAO = ("Locução de vídeo curto de explicação, em português do Brasil. Ritmo ágil e direto, "
           "sem pausas longas entre as frases, com a mesma energia do começo ao fim:")


@dataclass(frozen=True)
class VozPronta:
    id: str                 # "gemini:Orus", "local:faber"
    nome: str
    descricao: str
    motor: str              # "gemini" ou "local"


#: As vozes do Gemini que a página oferece (o catálogo dele tem 30; estas cobrem os jeitos de
#: narrar um vídeo de explicação).
VOZES_DO_GEMINI = (
    VozPronta("gemini:Orus", "Orus", "masculina, firme, de locutor", "gemini"),
    VozPronta("gemini:Charon", "Charon", "masculina, de quem explica", "gemini"),
    VozPronta("gemini:Puck", "Puck", "masculina, animada", "gemini"),
    VozPronta("gemini:Kore", "Kore", "feminina, firme", "gemini"),
    VozPronta("gemini:Aoede", "Aoede", "feminina, leve", "gemini"),
    VozPronta("gemini:Leda", "Leda", "feminina, jovem", "gemini"),
)
VOZ_LOCAL = VozPronta("local:faber", "Faber", "masculina, no seu computador, sem internet",
                      "local")


class SemVoz(RuntimeError):
    """A narração não saiu (a mensagem diz por quê, para a página)."""


def vozes() -> list[VozPronta]:
    return [*VOZES_DO_GEMINI, VOZ_LOCAL]


def achar(voz_id: str) -> VozPronta:
    v = next((v for v in vozes() if v.id == voz_id), None)
    if v is None:
        raise SemVoz("Voz pronta desconhecida.")
    return v


# ── a cota do Gemini ─────────────────────────────────────────────────────


def _registro() -> Path:
    return ia.pasta_de_dados() / "narracoes-do-gemini.json"


def _hoje() -> str:
    # a cota grátis do Gemini volta à meia-noite UTC
    return datetime.now(UTC).date().isoformat()


def usadas_hoje() -> int:
    try:
        dados = json.loads(_registro().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    return int(dados.get(_hoje(), 0)) if isinstance(dados, dict) else 0


def restantes_hoje() -> int:
    return max(0, POR_DIA - usadas_hoje())


def _anotar_narracao() -> None:
    try:
        caminho = _registro()
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(json.dumps({_hoje(): usadas_hoje() + 1}), encoding="utf-8")
    except OSError:
        logger.debug("não deu para anotar a narração", exc_info=True)


def estado() -> dict:
    """O que a página mostra das vozes prontas: quais existem, e o que falta para cada uma."""
    return {"vozes": [{"id": v.id, "nome": v.nome, "descricao": v.descricao, "motor": v.motor}
                      for v in vozes()],
            "gemini": {"ligado": ia.gemini_pronto(), "restantes_hoje": restantes_hoje(),
                       "por_dia": POR_DIA},
            "local": voz_local.estado()}


# ── o Gemini ─────────────────────────────────────────────────────────────


def _pedido_do_gemini(texto: str, nome_da_voz: str) -> dict:
    return {"contents": [{"parts": [{"text": f"{DIRECAO} {texto}"}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {
                                     "voiceName": nome_da_voz}}}}}


def _pcm_do_gemini(texto: str, nome_da_voz: str, *, transporte=None) -> bytes:
    """O áudio de um pedido (PCM de 16 bits, mono, 24 kHz)."""
    import httpx

    chave, _origem = ia.chave()
    if not chave:
        raise SemVoz("A voz do Gemini precisa da chave do Gemini (em \"Antes de começar\").")
    try:
        with httpx.Client(transport=transporte, timeout=300.0) as cliente:
            r = cliente.post(f"{ia.API}/models/{MODELO_TTS}:generateContent",
                             json=_pedido_do_gemini(texto, nome_da_voz),
                             headers={"x-goog-api-key": chave})
    except httpx.TimeoutException as erro:
        raise SemVoz("O Gemini demorou demais para narrar. Tente de novo.") from erro
    except httpx.HTTPError as erro:
        raise SemVoz("Não consegui falar com o Gemini. Confira a internet.") from erro
    if r.status_code == 429:
        espera = ia._espera_da_cota(r)
        volta = f" Ela volta em {ia._daqui_a(espera)}." if espera else ""
        raise SemVoz(f"A cota de voz do Gemini acabou por hoje ({POR_DIA} narrações por dia na "
                     f"chave grátis).{volta} Use a voz local ou a sua.")
    if r.status_code in (401, 403):
        raise SemVoz("O Google recusou a chave do Gemini. Troque a chave em \"Antes de começar\".")
    if r.status_code >= 400:
        raise SemVoz(f"O Gemini não narrou ({r.status_code}): {ia._mensagem_do_google(r)}")
    try:
        partes = r.json()["candidates"][0]["content"]["parts"]
        dados = next(p["inlineData"]["data"] for p in partes if "inlineData" in p)
    except (ValueError, KeyError, IndexError, StopIteration) as erro:
        raise SemVoz("O Gemini respondeu sem o áudio. Tente de novo.") from erro
    _anotar_narracao()
    return base64.b64decode(dados)


def partes_do_gemini(roteiro: str) -> list[str]:
    """O roteiro em pedidos: os parágrafos juntos até ``LETRAS_POR_PEDIDO`` letras."""
    grupos: list[str] = []
    for paragrafo in re.split(r"\n\s*\n", roteiro.strip()):
        texto = re.sub(r"\s+", " ", paragrafo).strip()
        if not texto:
            continue
        if grupos and len(grupos[-1]) + 2 + len(texto) <= LETRAS_POR_PEDIDO:
            grupos[-1] += "\n\n" + texto
        else:
            grupos.append(texto)
    return grupos


def _do_pcm(pcm: bytes) -> np.ndarray:
    x = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
    if voz_clonada.TAXA != TAXA_DO_GEMINI and len(x):
        # reamostragem linear simples: a voz já vem em 24 kHz e o editor fala em 48 kHz
        n = round(len(x) * voz_clonada.TAXA / TAXA_DO_GEMINI)
        x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)
    return x


def _tom(segundos: float) -> np.ndarray:
    """A IA falsa dos testes: um tom da duração que a fala teria."""
    n = max(1, round(segundos * voz_clonada.TAXA))
    t = np.arange(n) / voz_clonada.TAXA
    return (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


# ── a narração ───────────────────────────────────────────────────────────


def narrar(voz_id: str, roteiro: str, destino: Path, *,
           pronuncia: dict[str, str] | None = None,
           progresso: Callable[[int, int], None] | None = None,
           parar: Callable[[], bool] | None = None, transporte=None) -> voz_clonada.Narracao:
    """O roteiro narrado pela voz pronta, em ``destino`` (WAV), com o roteiro ao lado."""
    v = achar(voz_id)
    roteiro = str(roteiro or "").strip()
    if not roteiro:
        raise SemVoz("O roteiro está vazio.")
    if len(roteiro) > voz_clonada.ROTEIRO_MAXIMO:
        raise SemVoz(f"O roteiro passa de {voz_clonada.ROTEIRO_MAXIMO} letras: divida em vídeos "
                     "menores.")
    lido = voz_clonada.aplicar_pronuncia(roteiro, pronuncia or {})
    if v.motor == "local":
        audio, total, reaproveitados, aparelho = _narrar_local(lido, progresso, parar)
    else:
        audio, total, reaproveitados, aparelho = _narrar_gemini(v, lido, progresso, parar,
                                                                transporte)
    audio = voz.limitar(voz.nivelar(audio, voz.FINAL_LUFS))
    destino = Path(destino)
    voz_clonada._gravar(destino, audio)
    destino.with_suffix(".roteiro.txt").write_text(roteiro, encoding="utf-8")
    return voz_clonada.Narracao(destino, round(len(audio) / voz_clonada.TAXA, 2), total,
                                reaproveitados, aparelho)


def _narrar_gemini(v: VozPronta, lido: str, progresso, parar, transporte):
    partes = partes_do_gemini(lido)
    cache = voz_clonada.pasta_das_narracoes()
    audios: list[np.ndarray] = []
    reaproveitados = 0
    for k, texto in enumerate(partes):
        if progresso:
            progresso(k, len(partes))
        if parar and parar():
            raise SemVoz("A narração foi cancelada.")
        chave = hashlib.sha1(f"{MODELO_TTS}|{v.id}|{DIRECAO}|{texto}".encode()).hexdigest()[:20]
        guardado = cache / f"gemini-{chave}.wav"
        if guardado.is_file():
            x = video_mod.ler_audio_mono(guardado, voz_clonada.TAXA)
            reaproveitados += 1
        elif ia.falsa():
            x = _tom(len(texto.split()) / 2.6)
        else:
            x = _do_pcm(_pcm_do_gemini(texto, v.nome, transporte=transporte))
            voz_clonada._gravar(guardado, x)
        x, _ = voz.aparar(x)
        if audios:
            audios.append(np.zeros(int(voz_clonada.ENTRE_PARAGRAFOS_S * voz_clonada.TAXA),
                                   np.float32))
        audios.append(x)
    if progresso:
        progresso(len(partes), len(partes))
    return np.concatenate(audios), len(partes), reaproveitados, "gemini"


def _narrar_local(lido: str, progresso, parar):
    blocos = voz_clonada.pedacos(lido)
    cache = voz_clonada.pasta_das_narracoes()
    planos: list[list[Path]] = []
    faltam: list[tuple[str, Path]] = []
    identidade = voz_local.identidade()
    for bloco in blocos:
        caminhos = []
        for pedaco in bloco:
            texto = voz_local.para_ler(pedaco)
            chave = hashlib.sha1(f"{identidade}|{texto}".encode()).hexdigest()[:20]
            arquivo = cache / f"local-{chave}.wav"
            if not arquivo.is_file() and all(arquivo != s for _t, s in faltam):
                faltam.append((texto, arquivo))
            caminhos.append(arquivo)
        planos.append(caminhos)
    total = sum(len(c) for c in planos)
    feitas_antes = total - len(faltam)
    if progresso:
        progresso(feitas_antes, total)
    aparelho = "guardado"
    if faltam:
        def andou(feitas: int, _n: int) -> None:
            if progresso:
                progresso(feitas_antes + feitas, total)

        try:
            aparelho = voz_local.sintetizar(faltam, progresso=andou, parar=parar)
        except voz_local.ErroDaVozLocal as erro:
            raise SemVoz(str(erro)) from erro
    partes: list[np.ndarray] = []
    for k, caminhos in enumerate(planos):
        if k:
            partes.append(np.zeros(int(voz_clonada.ENTRE_PARAGRAFOS_S * voz_clonada.TAXA),
                                   np.float32))
        for m, c in enumerate(caminhos):
            if m:
                partes.append(np.zeros(int(voz_clonada.ENTRE_FRASES_S * voz_clonada.TAXA),
                                       np.float32))
            x, _ = voz.aparar(video_mod.ler_audio_mono(c, voz_clonada.TAXA))
            partes.append(x)
    return np.concatenate(partes), total, feitas_antes, aparelho


__all__ = [
    "DIRECAO",
    "MODELO_TTS",
    "POR_DIA",
    "VOZES_DO_GEMINI",
    "VOZ_LOCAL",
    "SemVoz",
    "VozPronta",
    "achar",
    "estado",
    "narrar",
    "partes_do_gemini",
    "restantes_hoje",
    "usadas_hoje",
    "vozes",
]
