"""
O avatar: um personagem em pixel art montado por partes, no padrão do apresentador do
um projeto anterior (``recursos/personagem/padrao.json``): as mesmas 12 poses, as 3 bocas da fala, a
regra da boca pelas sílabas e a pose por frase.

- **As partes** ficam em ``recursos/personagem/partes`` — uma cópia do repositório público
  `editai-personagens <https://github.com/lucasteles1231/editai-personagens>`_, num commit
  fixo (o ``LEIA-ME.md`` diz qual). O ``catalogo.json`` diz o que cada uma é e quais cores ela
  usa. É a lógica dos jogos de montar personagem: um cabelo, uma barba, uns óculos, uma roupa,
  e as cores de cada coisa.
- **A página monta e desenha** (``web/src/avatar/desenhar.ts``); o servidor só guarda os 36
  quadros aprovados (12 poses × 3 bocas, 900 × 900) e o que foi escolhido, para reabrir.
- **Pela foto:** o Gemini (cota grátis) olha a foto e escolhe uma parte de cada categoria e as
  cores, só entre as opções do catálogo. O que vier fora dele vira o padrão. A foto não é
  guardada.
- **No vídeo** (``montagem.CamadaDeAvatar``): a pose muda a cada frase
  (:func:`poses_das_falas`) e a boca abre nas sílabas (:func:`bocas_por_quadro`).

Por que partes, e não uma IA de imagem a cada quadro: num projeto anterior, a IA redesenhava a imagem
inteira só para abrir a boca, e o personagem tremia; aqui cada quadro é a mesma montagem com
uma peça trocada, não custa nada e pode ser refeito a qualquer hora.
"""
from __future__ import annotations

import io
import json
import re
import shutil
import time
import unicodedata
import zipfile
from collections.abc import Sequence
from functools import cache
from importlib.resources import files
from pathlib import Path

import numpy as np

NOME_MAXIMO = 40
#: O teto de cada quadro enviado (um PNG de 900 × 900 em pixel art tem uns 30 KB).
QUADRO_TETO_BYTES = 3 * 1024 * 1024
#: O teto da foto mandada ao Gemini, e o lado dela no pedido.
FOTO_TETO_BYTES = 20 * 1024 * 1024
FOTO_LADO = 1024
COR = re.compile(r"#[0-9a-fA-F]{6}")


class AvatarInvalido(ValueError):
    """O nome, as partes ou os quadros não servem (a mensagem diz por quê)."""


# ── o padrão e o catálogo ────────────────────────────────────────────────


def _recurso(nome: str) -> dict:
    return json.loads(files("editor").joinpath("recursos", "personagem", nome)
                      .read_text(encoding="utf-8"))


@cache
def padrao() -> dict:
    return _recurso("padrao.json")


@cache
def catalogo() -> dict:
    return _recurso("catalogo.json")


def poses() -> list[str]:
    return list(padrao()["poses"])


def bocas() -> list[str]:
    return list(padrao()["pacote"]["bocas"])


def nomes_dos_quadros() -> list[str]:
    """Os 36 nomes do pacote, na ordem das poses: "neutro_fechada.png"…"""
    return [padrao()["pacote"]["nome_do_quadro"].format(pose=p, boca=b)
            for p in poses() for b in bocas()]


def escolhas_validas(dados: dict | None) -> dict:
    """As escolhas no formato do desenhista da página, conferidas contra o catálogo: um id
    que não existe vira o padrão, uma cor que não é ``#rrggbb`` também. As partes fixas (o
    manequim, os olhos, a boca e os braços das poses) não se escolhem."""
    dados = dados if isinstance(dados, dict) else {}
    cat = catalogo()
    padrao_ = cat["padrao"]
    saida: dict = dict(cat["fixas"])
    for categoria, info in cat["categorias"].items():
        ids = {o["id"] for o in info["opcoes"]} | {"nenhum"}
        valor = dados.get(categoria)
        saida[categoria] = valor if valor in ids else padrao_[categoria]
    # um bicho troca a cabeça, os olhos e a boca juntos, e as partes da cabeça humana (cabelo,
    # barba, sobrancelha, óculos, acessório) saem: elas não encaixam nele
    bicho = dados.get("cabeca")
    if bicho in {b["id"] for b in cat.get("bichos", [])}:
        saida.update(cabeca=bicho, olhos=bicho, boca=bicho, sobrancelhas="nenhum")
        for categoria in ("cabelo", "barba", "oculos", "acessorio"):
            saida[categoria] = "nenhum"
    cores_ = dados.get("cores") if isinstance(dados.get("cores"), dict) else {}
    saida["cores"] = {}
    for espaco, cor_padrao in padrao_["cores"].items():
        valor = str(cores_.get(espaco) or "")
        vazia_vale = "vazia" in cat["cores"].get(espaco, {})   # sobrancelha e barba: do cabelo
        if COR.fullmatch(valor):
            saida["cores"][espaco] = valor.lower()
        else:
            saida["cores"][espaco] = "" if vazia_vale and not valor else cor_padrao
    return saida


# ── os avatares salvos ───────────────────────────────────────────────────


def pasta_dos_avatares() -> Path:
    from editor.ia import pasta_de_dados

    return pasta_de_dados() / "avatares"


def nome_valido(nome: str) -> str:
    limpo = re.sub(r"\s+", " ", str(nome or "")).strip()
    if not limpo:
        raise AvatarInvalido("Dê um nome ao avatar.")
    if len(limpo) > NOME_MAXIMO:
        raise AvatarInvalido(f"O nome passa de {NOME_MAXIMO} letras.")
    if not re.fullmatch(r"[^\W_]+(?:[ '’-][^\W_]+)*", limpo):
        raise AvatarInvalido("O nome leva só letras, números, espaços, hífen e apóstrofo.")
    return limpo


def apelido(nome: str) -> str:
    """O nome da pasta: "Lucas Teles" vira "lucas-teles"."""
    t = "".join(c for c in unicodedata.normalize("NFKD", nome.lower())
                if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:60] or "avatar"


def _conferir_quadro(nome: str, dados: bytes) -> None:
    from PIL import Image

    if len(dados) > QUADRO_TETO_BYTES:
        raise AvatarInvalido(f"O quadro {nome} passa de 3 MB.")
    try:
        img = Image.open(io.BytesIO(dados))
        formato, tamanho = img.format, img.size
        img.load()
    except Exception as erro:
        raise AvatarInvalido(f"O quadro {nome} não é uma imagem.") from erro
    lado = padrao()["quadro"]["lado"]
    if formato != "PNG" or tamanho != (lado, lado):
        raise AvatarInvalido(f"O quadro {nome} precisa ser um PNG de {lado} × {lado}.")


def _caixa(dados: bytes) -> dict:
    """O que aparece de um quadro (a silhueta), em frações dele: é por ela que a thumbnail
    encaixa o avatar, como faz com a pessoa recortada."""
    from PIL import Image

    alfa = np.asarray(Image.open(io.BytesIO(dados)).convert("RGBA"))[..., 3]
    ys, xs = np.nonzero(alfa > 0)
    h, w = alfa.shape
    if not len(ys):
        return {"x0": 0.0, "y0": 0.0, "x1": 1.0, "y1": 1.0}
    return {"x0": round(xs.min() / w, 4), "y0": round(ys.min() / h, 4),
            "x1": round((xs.max() + 1) / w, 4), "y1": round((ys.max() + 1) / h, 4)}


def rosto() -> dict:
    """Onde fica o rosto em todo quadro (a cabeça não sai do lugar): dos marcos do manequim,
    do alto da cabeça ao queixo, em frações do quadro."""
    m = _recurso_partes("extracao.json")["marcos"]
    grade = padrao()["quadro"]["grade"]
    return {"x0": round(m["rosto_x"][0] / grade, 4), "y0": round(m["topo"] / grade, 4),
            "x1": round((m["rosto_x"][1] + 1) / grade, 4), "y1": round(m["roupa_desde"] / grade, 4)}


def _recurso_partes(nome: str) -> dict:
    return json.loads(files("editor").joinpath("recursos", "personagem", "partes", nome)
                      .read_text(encoding="utf-8"))


def salvar(nome: str, escolhas: dict, quadros: dict[str, bytes]) -> dict:
    """O avatar aprovado: as escolhas e os 36 quadros desenhados na página (o mesmo nome
    substitui o anterior)."""
    nome = nome_valido(nome)
    faltam = [n for n in nomes_dos_quadros() if n not in quadros]
    if faltam:
        raise AvatarInvalido(f"Faltam {len(faltam)} quadros (o primeiro: {faltam[0]}).")
    sobram = sorted(set(quadros) - set(nomes_dos_quadros()))
    if sobram:
        raise AvatarInvalido(f"Quadro desconhecido: {sobram[0]}.")
    for n, dados in quadros.items():
        _conferir_quadro(n, dados)
    slug = apelido(nome)
    final = pasta_dos_avatares() / slug
    nova = pasta_dos_avatares() / f".{slug}-novo"
    shutil.rmtree(nova, ignore_errors=True)
    (nova / "quadros").mkdir(parents=True)
    for n, dados in quadros.items():
        (nova / "quadros" / n).write_bytes(dados)
    modelo = padrao()["pacote"]["nome_do_quadro"]
    info = {"nome": nome, "apelido": slug, "criado": time.strftime("%Y-%m-%d %H:%M:%S"),
            "padrao": padrao()["versao"], "escolhas": escolhas_validas(escolhas),
            "caixas": {pose: _caixa(quadros[modelo.format(pose=pose, boca="fechada")])
                       for pose in poses()},
            "rosto": rosto()}
    (nova / "avatar.json").write_text(json.dumps(info, ensure_ascii=False, indent=1),
                                      encoding="utf-8")
    shutil.rmtree(final, ignore_errors=True)
    nova.rename(final)
    return info


def avatares() -> list[dict]:
    pasta = pasta_dos_avatares()
    if not pasta.is_dir():
        return []
    saida = []
    for d in sorted(pasta.iterdir()):
        if d.name.startswith(".") or not (d / "avatar.json").is_file():
            continue
        try:
            saida.append(json.loads((d / "avatar.json").read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return saida


def _pasta(slug: str) -> Path:
    if not re.fullmatch(r"[a-z0-9-]{1,60}", slug or ""):
        raise AvatarInvalido("Avatar desconhecido.")
    pasta = pasta_dos_avatares() / slug
    if not (pasta / "avatar.json").is_file():
        raise AvatarInvalido("Esse avatar não existe (ou foi apagado).")
    return pasta


def achar(nome_ou_slug: str) -> str:
    """O apelido de um avatar salvo, pelo nome ("Lucas Teles") ou pelo apelido."""
    slug = apelido(str(nome_ou_slug or ""))
    _pasta(slug)
    return slug


def ler(slug: str) -> dict:
    return json.loads((_pasta(slug) / "avatar.json").read_text(encoding="utf-8"))


def quadro(slug: str, nome: str) -> Path:
    if nome not in nomes_dos_quadros():
        raise AvatarInvalido("Quadro desconhecido.")
    caminho = _pasta(slug) / "quadros" / nome
    if not caminho.is_file():
        raise AvatarInvalido("Esse quadro não existe.")
    return caminho


def apagar(slug: str) -> None:
    shutil.rmtree(_pasta(slug))


def _leia_me(info: dict) -> str:
    p = padrao()
    linhas = [f"O avatar {info['nome']}, feito no Editai em {info['criado']}.", "",
              f"São {len(nomes_dos_quadros())} quadros de {p['quadro']['lado']} × "
              f"{p['quadro']['lado']}, fundo transparente, a cabeça sempre no mesmo lugar: "
              "trocar de pose não faz o personagem pular.", "",
              "O nome de cada quadro é a pose e a boca: neutro_fechada.png, neutro_meia.png, "
              "neutro_aberta.png…", "",
              "AS BOCAS (para a fala):",
              "- fechada: a boca da expressão da pose;",
              "- meia: abre e fecha cada sílaba, e é a da sílaba fraca;",
              "- aberta: o meio da sílaba forte.",
              "A boca abre um quadro antes de cada sílaba, sempre pela meia. num projeto anterior, "
              "ela ficou 57% do tempo fechada, 26% meia e 17% aberta.", "",
              "AS POSES (uma por frase):"]
    for nome, pose in p["poses"].items():
        linhas.append(f"- {nome}: {pose['descricao']} — {pose['quando']}")
    linhas += ["", "A pose aponta para a direita do quadro (apontando_lado). Do lado direito "
               "da tela, espelhe o avatar: ele aponta para o meio.", "",
               "O padrão inteiro está no padrao.json, junto. As partes do avatar são do "
               "repositório editai-personagens (CC0)."]
    return "\n".join(linhas) + "\n"


def pacote(slug: str) -> bytes:
    """O zip para baixar: os 36 quadros, o ``avatar.json``, o padrão e um LEIA-ME."""
    pasta = _pasta(slug)
    info = ler(slug)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n in nomes_dos_quadros():
            z.write(pasta / "quadros" / n, f"{slug}/{n}")
        z.writestr(f"{slug}/avatar.json", json.dumps(info, ensure_ascii=False, indent=1))
        z.writestr(f"{slug}/padrao.json", json.dumps(padrao(), ensure_ascii=False, indent=1))
        z.writestr(f"{slug}/LEIA-ME.txt", _leia_me(info))
    return buf.getvalue()


# ── pela foto, com o Gemini ──────────────────────────────────────────────


SISTEMA = """Você monta avatares em pixel art a partir de uma foto, como nos jogos de montar
personagem: escolhe uma peça de cada categoria, entre opções fechadas, e as cores. Você não
desenha. Responda só com o JSON pedido."""


def _foto_jpeg(foto: bytes) -> bytes:
    """A foto em JPEG, com no máximo ``FOTO_LADO`` de lado e sem os metadados (o lugar e o
    aparelho ficam de fora)."""
    from PIL import Image, ImageOps

    if len(foto) > FOTO_TETO_BYTES:
        raise AvatarInvalido("A foto passa de 20 MB.")
    try:
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(foto))).convert("RGB")
    except Exception as erro:
        raise AvatarInvalido("Não consegui abrir a foto. Use um JPG ou um PNG.") from erro
    img.thumbnail((FOTO_LADO, FOTO_LADO))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    return buf.getvalue()


def pedido_das_partes() -> tuple[str, dict]:
    """O texto do pedido (o catálogo descrito em inglês) e o esquema da resposta."""
    cat = catalogo()
    linhas, campos = [], {}
    for categoria, info in cat["categorias"].items():
        opcoes = [f'  - "{o["id"]}": {o["en"]}' for o in info["opcoes"]]
        opcoes.append(f'  - "nenhum": {info["nenhum"]["en"]}')
        linhas.append(f"{categoria.upper()} (one of):\n" + "\n".join(opcoes))
        # enums pequenos (até 16): o enum grande dá 400 genérico nos modelos 3.x
        campos[categoria] = {"type": "string",
                             "enum": [o["id"] for o in info["opcoes"]] + ["nenhum"]}
    for espaco in ("pele", "cabelo", "barba", "olho", "roupa"):
        campos[f"cor_{espaco}"] = {"type": "string", "description": "#rrggbb"}
    campos["descricao"] = {"type": "string",
                           "description": "a pessoa em uma frase, em português"}
    sugestoes = "\n".join(
        f"- {espaco}: " + ", ".join(f"{hex_} ({nome})" for hex_, nome in
                                    info["sugestoes"].items())
        for espaco, info in cat["cores"].items() if espaco in ("pele", "cabelo", "olho"))
    texto = f"""The photo above shows a person. Build their avatar from the parts below: pick
the ONE option of each category that looks most like the person (the hair shape and length,
the facial hair, the glasses, a hat or headphones, the top they wear). When the person has
no glasses, no hat or no beard, pick "nenhum".

{chr(10).join(linhas)}

COLORS: give each color as #rrggbb, as it looks in the photo, a bit more saturated, like
pixel art (cor_pele: the skin; cor_cabelo: the hair, or the eyebrows when bald; cor_barba:
the facial hair, or "" when there is none; cor_olho: the iris; cor_roupa: the top). These are
good references:
{sugestoes}

"descricao": the person in one short sentence, in Brazilian Portuguese."""
    return texto, {"type": "object", "properties": campos, "required": list(campos)}


def escolher_partes(foto: bytes, *, transporte=None) -> dict:
    """As partes e as cores do avatar pela foto: ``{"escolhas", "descricao", "por"}``.

    Sem a chave, levanta :class:`editor.ia.ErroDaIA`; com a IA falsa (os testes), devolve o
    padrão."""
    from editor import ia

    jpeg = _foto_jpeg(foto)
    if ia.falsa():
        return {"escolhas": escolhas_validas({}), "descricao": "a IA falsa dos testes",
                "por": "falsa"}
    texto, esquema = pedido_das_partes()
    resposta, modelo = ia.perguntar_json(SISTEMA, texto, esquema, temperatura=0.2,
                                         imagens=[jpeg], transporte=transporte)
    escolhas = {k: resposta.get(k) for k in catalogo()["categorias"]}
    escolhas["cores"] = {espaco: resposta.get(f"cor_{espaco}", "")
                         for espaco in ("pele", "cabelo", "barba", "olho", "roupa")}
    return {"escolhas": escolhas_validas(escolhas),
            "descricao": str(resposta.get("descricao") or "")[:200], "por": modelo}


# ── a fala: a boca pelas sílabas ─────────────────────────────────────────


def _picos(env: np.ndarray, altura: float, proeminencia: float, distancia: int
           ) -> np.ndarray:
    """Os picos de ``env`` como o ``scipy.signal.find_peaks`` de um projeto anterior acha (altura,
    distância e proeminência, nessa ordem), sem o scipy."""
    if len(env) < 3:
        return np.zeros(0, int)
    # o máximo local; num platô, o meio dele (como o scipy)
    candidatos = []
    i = 1
    while i < len(env) - 1:
        if env[i] > env[i - 1]:
            j = i
            while j + 1 < len(env) and env[j + 1] == env[i]:
                j += 1
            if j + 1 < len(env) and env[j + 1] < env[i]:
                candidatos.append((i + j) // 2)
            i = j + 1
        else:
            i += 1
    picos = np.array([p for p in candidatos if env[p] >= altura], int)
    if len(picos) and distancia > 1:
        # os mais altos primeiro; um pico perto demais de um já guardado sai
        manter = np.ones(len(picos), bool)
        for k in np.argsort(-env[picos], kind="stable"):
            if not manter[k]:
                continue
            perto = np.abs(picos - picos[k]) < distancia
            perto[k] = False
            manter[perto] = False
        picos = picos[manter]
    saida = []
    for p in picos:
        e = p
        while e > 0 and env[e - 1] <= env[p]:
            e -= 1
        esquerda = env[e:p + 1].min()
        r = p
        while r < len(env) - 1 and env[r + 1] <= env[p]:
            r += 1
        direita = env[p:r + 1].min()
        if env[p] - max(esquerda, direita) >= proeminencia:
            saida.append(p)
    return np.array(saida, int)


def silabas(x: np.ndarray, taxa: int) -> tuple[list[float], np.ndarray, float]:
    """Os instantes das sílabas (os picos do envelope de 25 ms, a cada 10 ms), o envelope
    normalizado e o passo dele, em segundos."""
    fala = padrao()["fala"]
    x = np.asarray(x, np.float64)
    if x.ndim > 1:
        x = x.mean(axis=1)
    passo = taxa * fala["passo_ms"] // 1000
    janela = taxa * fala["envelope_ms"] // 1000
    n = max(0, (len(x) - janela) // passo + 1)
    if n == 0:
        return [], np.zeros(0), passo / taxa
    quadros = np.lib.stride_tricks.sliding_window_view(x, janela)[::passo][:n]
    env = np.sqrt((quadros ** 2).mean(axis=1))
    env = np.convolve(env, np.ones(3) / 3, mode="same")
    env = env / (np.percentile(env, 90) or 1.0)
    pico = fala["pico"]
    picos = _picos(env, pico["altura"], pico["proeminencia"],
                   max(1, round(pico["distancia_ms"] / fala["passo_ms"])))
    return [(p * passo + janela / 2) / taxa for p in picos], env, passo / taxa


def bocas_por_quadro(x: np.ndarray, taxa: int, fps: float, total: int) -> list[str]:
    """A boca de cada quadro ("fechada", "meia" ou "aberta"), a regra de um projeto anterior: abre um
    quadro antes do pico de cada sílaba, sempre pela meia, e fica aberta enquanto a vogal se
    sustenta, fechando pelo menos dois quadros antes da sílaba seguinte. A sílaba fraca
    (abaixo de 0,85 da mediana das vizinhas) abre só até a meia."""
    fala = padrao()["fala"]
    boca = ["fechada"] * total
    picos, env, passo = silabas(x, taxa)
    if not picos:
        return boca

    def volume(q: int) -> float:
        i0, i1 = int(q / fps / passo), int((q + 1) / fps / passo)
        trecho = env[i0:max(i1, i0 + 1)]
        return float(trecho.max()) if len(trecho) else 0.0

    minimo, maximo = fala["aberta_quadros"]
    quadros = [round(p * fps) for p in picos]
    forcas = [volume(q) for q in quadros]
    for i, q in enumerate(quadros):
        prox = quadros[i + 1] if i + 1 < len(quadros) else q + 12
        teto = max(minimo, min(maximo, prox - q - 2))
        dur = minimo
        while dur < teto and volume(q - 1 + dur) > fala["sustenta"] * forcas[i]:
            dur += 1
        vizinhas = forcas[max(0, i - fala["vizinhas"]):i + fala["vizinhas"] + 1]
        fraca = forcas[i] < fala["fraca"] * float(np.median(vizinhas))
        for n, k in enumerate(range(max(0, q - fala["abre_antes_quadros"]),
                                    min(total, q - 1 + dur))):
            borda = n == 0 or (n == dur - 1 and dur >= 3)
            boca[k] = "meia" if fraca or borda else "aberta"
    return boca


# ── a pose de cada frase ─────────────────────────────────────────────────


def _cru(texto: str) -> str:
    t = unicodedata.normalize("NFD", texto.lower())
    return " " + re.sub(r"\s+", " ", "".join(c for c in t if unicodedata.category(c) != "Mn")) + " "


#: As regras, na ordem: a primeira que bate escolhe a pose (o "quando" do padrão).
REGRAS: list[tuple[str, re.Pattern]] = [
    ("rindo", re.compile(r"\b(ha){2,}|\bk{3,}|\brs(rs)+|risada|piada")),
    ("surpreso", re.compile(r"\b(incrivel|nossa|uau|caramba|serio\?|chocante|acredita)")),
    ("pensando", re.compile(r"\?|\bsera que\b")),
    ("apontando_voce", re.compile(r"\b(voce|voces|te|teu|tua|seu|sua|vem|venha)\b")),
    ("mao_no_peito", re.compile(r"\b(eu|meu|minha|meus|minhas|sinceramente|confesso)\b")),
    ("apontando_lado", re.compile(r"\b(olha|olhe|aqui|veja|repara|isso aqui|na tela)\b")),
    ("joinha", re.compile(r"\b(pronto|funciona|perfeito|e isso|certo|beleza|top)\b")),
    ("cafe", re.compile(r"\b(calma|tranquilo|relaxa|devagar|sem pressa)\b")),
    ("bracos_cruzados", re.compile(r"\b(simples assim|com certeza|obviamente|claro que)\b")),
    ("apontando_cima", re.compile(r"!|\d|\b(importante|atencao|dica|primeiro|segredo)\b")),
]


def pose_da_fala(texto: str, anterior: str | None = None) -> str:
    """A pose de uma frase pela regra local (sem Gemini): a primeira regra que bate; sem
    nenhuma, explicando ou neutro, sem repetir a anterior."""
    cru = _cru(texto)
    for pose, regra in REGRAS:
        if regra.search(cru):
            return pose
    if anterior is None:
        return "neutro"
    return "neutro" if anterior == "explicando" else "explicando"


#: Uma frase nova começa depois de um ponto final ou de uma pausa desta (s).
PAUSA_DE_FRASE_S = 0.7
#: Numa frase comprida, a vírgula também troca a pose, depois deste tempo: "Você já perdeu
#: horas editando seus vídeos, cortando silêncios, criando legendas…" ficava 6 s numa pose só
#: (medido num vídeo do dono, em 20/10/2026).
PEDACO_S = 1.5
#: Uma frase mais curta que isto fica com a pose da anterior: trocar a cada meio segundo
#: parece tique.
FRASE_MINIMA_S = 1.2


def poses_das_falas(blocos: Sequence) -> list[tuple[float, float, str]]:
    """``(início, fim, pose)`` de cada frase da legenda, no tempo do vídeo editado: as
    palavras dos blocos juntadas até o fim de frase, uma pausa ou, passado :data:`PEDACO_S`,
    uma vírgula; cada frase com a pose dela. A pose vale até a frase seguinte começar."""
    palavras = [w for b in blocos for w in b.palavras]
    frases: list[list] = []
    for w in palavras:
        anterior = frases[-1][-1].texto.rstrip() if frases else ""
        if (not frases or anterior.endswith((".", "?", "!", "…"))
                or w.inicio - frases[-1][-1].fim > PAUSA_DE_FRASE_S
                or (anterior.endswith((",", ";", ":"))
                    and frases[-1][-1].fim - frases[-1][0].inicio >= PEDACO_S)):
            frases.append([w])
        else:
            frases[-1].append(w)
    saida: list[tuple[float, float, str]] = []
    anterior = None
    for frase in frases:
        texto = " ".join(w.texto for w in frase)
        ini, fim = frase[0].inicio, frase[-1].fim
        if saida and fim - ini < FRASE_MINIMA_S:
            a0, _a1, p = saida[-1]
            saida[-1] = (a0, fim, p)
            continue
        pose = pose_da_fala(texto, anterior)
        saida.append((ini, fim, pose))
        anterior = pose
    # cada pose vale até a próxima frase começar
    return [(a0, saida[i + 1][0] if i + 1 < len(saida) else a1, p)
            for i, (a0, a1, p) in enumerate(saida)]


__all__ = ["AvatarInvalido", "achar", "apagar", "apelido", "avatares", "bocas",
           "bocas_por_quadro", "catalogo", "escolhas_validas", "escolher_partes", "ler",
           "nomes_dos_quadros", "pacote", "padrao", "pose_da_fala", "poses",
           "poses_das_falas", "quadro", "salvar", "silabas"]
