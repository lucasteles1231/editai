"""
O roteiro pelo tema: a IA escreve a narração a partir de uma frase, a pessoa revisa e só então
a voz narra. É o começo do vídeo feito só pelo tema.

- **Um pedido só**, de texto, pelo mesmo caminho dos cartões (``ia.perguntar_json``), no
  modelo principal: o roteiro pede o melhor que escreve, mesmo levando de 1 a 2 minutos (o
  flash-latest pensando, medido em 25/10/2026).
- **O tamanho** sai do tempo pedido: ~2,6 palavras por segundo de fala (a mesma medida da
  página), então 45 s são ~117 palavras. Uma resposta que passa de 25% para mais ou para
  menos volta uma vez para o conserto.
- **No Auto** (sem tempo pedido), a IA escreve no tamanho que o assunto pede, o mais curto que
  explica bem, sem passar do ``teto`` (o limite da plataforma). Passou, volta para o
  conserto.
- **As regras de um vídeo curto que segura a atenção:**
  - a primeira frase é o gancho (uma pergunta ou um fato que intriga), sem "você sabia" e sem
    "neste vídeo";
  - as frases são curtas;
  - os parágrafos têm de 1 a 3 frases e um assunto cada, porque cada parágrafo vira um bloco
    (as fotos e a pose do avatar mudam nele);
  - nenhum número de que o modelo não tenha certeza;
  - termina com uma pergunta ou uma chamada para comentar.
- **Sem a IA não há roteiro:** o motivo vai para a página.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from editor import ia

logger = logging.getLogger(__name__)

#: Quantas palavras se falam por segundo (a mesma conta de ``PassoEnvio.tsx``).
PALAVRAS_POR_SEGUNDO = 2.6
#: A folga do tamanho, para mais ou para menos, antes de pedir o conserto.
FOLGA = 0.25
SEGUNDOS_MINIMOS, SEGUNDOS_MAXIMOS = 15, 600
TEMA_MAXIMO = 300
TITULO_MAXIMO = 80
#: Os começos gastos que derrubam a retenção nos primeiros segundos.
GANCHOS_GASTOS = ("você sabia", "voce sabia", "neste vídeo", "neste video", "no vídeo de hoje",
                  "no video de hoje", "fala galera", "olá pessoal", "ola pessoal", "oi pessoal",
                  "hoje eu vou", "hoje vamos", "sem mais delongas", "bem-vindos", "bem vindos")

SISTEMA = """Você escreve a narração de vídeos curtos de explicação (Shorts, Reels, TikTok e
YouTube), que uma voz vai ler em voz alta. Escreva só o que é falado: nada de indicação de
cena, de música ou de câmera. Responda só com o JSON pedido."""


class SemRoteiro(RuntimeError):
    """Não deu para escrever o roteiro (a mensagem diz por quê, para a página)."""


@dataclass
class Roteiro:
    titulo: str
    paragrafos: list[str] = field(default_factory=list)
    #: Quem escreveu: "gemini", "falsa"…
    por: str = ""
    pedidos: int = 0
    modelo: str = ""

    @property
    def texto(self) -> str:
        """Os parágrafos separados por uma linha em branco (como a página e a voz leem)."""
        return "\n\n".join(self.paragrafos)

    @property
    def palavras(self) -> int:
        return len(self.texto.split())

    def para_dict(self) -> dict:
        return {"titulo": self.titulo, "texto": self.texto, "paragrafos": self.paragrafos,
                "palavras": self.palavras, "por": self.por, "pedidos": self.pedidos,
                "modelo": self.modelo}


def palavras_alvo(segundos: float) -> int:
    return round(_segundos(segundos) * PALAVRAS_POR_SEGUNDO)


def _segundos(segundos: float) -> float:
    return min(max(float(segundos), SEGUNDOS_MINIMOS), SEGUNDOS_MAXIMOS)


def esquema() -> dict:
    return {"type": "object", "properties": {
        "titulo": {"type": "string", "description": "o título do vídeo, até 60 letras"},
        "paragrafos": {"type": "array", "items": {"type": "string"}}},
        "required": ["titulo", "paragrafos"]}


def _tamanho(segundos: float | None, teto: float | None) -> tuple[str, bool]:
    """O tamanho pedido, em palavras, e se o vídeo é curto (o fim é uma pergunta)."""
    if segundos is not None:
        fala = round(_segundos(segundos))
        return (f"com uns {palavras_alvo(segundos)} palavras no total (uns {fala} s de fala)",
                _segundos(segundos) <= 90)
    limite = _segundos(teto or SEGUNDOS_MAXIMOS)
    texto = ("no tamanho que o assunto pede: o mais curto que explica bem, com começo, meio e "
             "fim")
    if limite <= 180:
        texto += (f". Um vídeo curto de explicação costuma dar de 30 a 60 s (de "
                  f"{palavras_alvo(30)} a {palavras_alvo(60)} palavras)")
    texto += f". Nunca passe de {palavras_alvo(limite)} palavras ({round(limite)} s de fala)"
    return texto, limite <= 180


def montar_pedido(tema: str, segundos: float | None, *, teto: float | None = None,
                  idioma: str = "pt") -> str:
    """O pedido do roteiro. Sem ``segundos`` (o Auto), no tamanho que o assunto pede, até o
    ``teto``."""
    lingua = {"pt": "português do Brasil", "en": "inglês", "es": "espanhol"}.get(idioma, idioma)
    tamanho, curto = _tamanho(segundos, teto)
    return f"""O tema do vídeo: {tema}

Escreva a narração em {lingua}, {tamanho}.

Regras:
- A primeira frase é o gancho: uma pergunta ou um fato que intriga e faz a pessoa ficar.
  Nunca comece com "você sabia", "neste vídeo", "fala, galera" nem com cumprimentos.
- Frases curtas, de fala, como alguém explicando para um amigo. Nada de lista nem de
  tópicos: é texto corrido.
- Divida em parágrafos de 1 a 3 frases, cada um com uma ideia só: cada parágrafo vira um
  trecho do vídeo, com a sua própria imagem.
- Explique o mecanismo, o porquê, com uma comparação do dia a dia quando ajudar.
- Números, datas e nomes só quando você tiver certeza. Na dúvida, explique sem o número.
  Nunca invente.
- Escreva os números como se fala ("dois mil e vinte", "trinta por cento") só quando for
  ambíguo; o resto pode ficar em algarismos.
- {"Termine com uma pergunta para quem assiste comentar." if curto else
   "Termine com uma frase que amarre a ideia principal e uma pergunta para quem assiste."}

"titulo": o título do vídeo, até 60 letras, sem ponto final.
"paragrafos": a narração, um parágrafo por item."""


def _limpo(texto) -> str:
    return re.sub(r"\s+", " ", str(texto or "")).strip()


def conferir(resposta: dict, segundos: float | None, *, teto: float | None = None
             ) -> tuple[Roteiro, list[str]]:
    """O roteiro que veio e o que precisa de conserto."""
    titulo = _limpo(resposta.get("titulo")).rstrip(".")[:TITULO_MAXIMO]
    paragrafos = [p for p in (_limpo(p) for p in resposta.get("paragrafos") or []) if p]
    roteiro = Roteiro(titulo=titulo, paragrafos=paragrafos)
    problemas = []
    if not paragrafos:
        return roteiro, ["não veio nenhum parágrafo"]
    if segundos is None:
        maximo = palavras_alvo(teto or SEGUNDOS_MAXIMOS)
        minimo = round(palavras_alvo(SEGUNDOS_MINIMOS) * (1 - FOLGA))
        if roteiro.palavras > maximo:
            problemas.append(f"o texto tem {roteiro.palavras} palavras e passa do limite de "
                             f"{maximo}")
        elif roteiro.palavras < minimo:
            problemas.append(f"o texto tem {roteiro.palavras} palavras: curto demais para "
                             "explicar o assunto")
    else:
        alvo = palavras_alvo(segundos)
        if abs(roteiro.palavras - alvo) > alvo * FOLGA:
            problemas.append(f"o texto tem {roteiro.palavras} palavras; precisa ter perto de "
                             f"{alvo}")
    comeco = paragrafos[0].lower()
    gasto = next((g for g in GANCHOS_GASTOS if comeco.startswith(g)), None)
    if gasto:
        problemas.append(f'a primeira frase começa com "{gasto}": troque por um gancho de verdade')
    if not titulo:
        problemas.append("faltou o título")
    return roteiro, problemas


def _falso(tema: str, segundos: float | None) -> Roteiro:
    """O roteiro da IA falsa dos testes: do tamanho pedido, sem rede."""
    frases = [f"Por que {tema.rstrip('?.!').lower()} funciona do jeito que funciona?",
              "A resposta começa num detalhe que quase ninguém repara.",
              "É ele que muda tudo, e a gente vai ver por quê.",
              "Primeiro, pense no caminho que cada parte faz.",
              "Depois, repare no que acontece quando uma delas falha.",
              "No fim, tudo se encaixa numa ideia simples.",
              "E você, já tinha reparado nisso?"]
    alvo = palavras_alvo(segundos if segundos is not None else 45)
    paragrafos, total, k = [], 0, 0
    while total < alvo * 0.9:
        frase = frases[k % len(frases)]
        paragrafos.append(frase)
        total += len(frase.split())
        k += 1
    return Roteiro(titulo=tema[:TITULO_MAXIMO], paragrafos=paragrafos, por="falsa")


def escrever(tema: str, segundos: float | None = 45, *, teto: float | None = None,
             idioma: str = "pt", transporte=None) -> Roteiro:
    """O roteiro do tema, para a pessoa revisar. Sem ``segundos`` (o Auto), no tamanho que
    o assunto pede, até o ``teto``. Levanta :class:`SemRoteiro` sem a IA."""
    tema = _limpo(tema)[:TEMA_MAXIMO]
    if not tema:
        raise SemRoteiro("Escreva o tema do vídeo, em uma frase.")
    if ia.falsa():
        return _falso(tema, segundos)
    if not ia.ligada():
        raise SemRoteiro("Para escrever o roteiro pelo tema, cole a chave do Gemini em \"Antes "
                         "de começar\". Ou marque Roteiro e escreva o texto.")
    pedido = montar_pedido(tema, segundos, teto=teto, idioma=idioma)
    gasto: list[str] = []
    try:
        resposta, modelo = ia.perguntar_json(SISTEMA, pedido, esquema(), temperatura=0.8,
                                             transporte=transporte, gasto=gasto)
    except ia.ErroDaIA as erro:
        raise SemRoteiro(str(erro)) from erro
    roteiro, problemas = conferir(resposta, segundos, teto=teto)
    if problemas:
        logger.info("conserto do roteiro pelo tema: %s", " | ".join(problemas))
        conserto = (pedido + "\n\nA RESPOSTA ANTERIOR TEVE ESTES PROBLEMAS. Mande o JSON inteiro "
                    "de novo, corrigido:\n" + "\n".join(f"- {p}" for p in problemas)
                    + "\n\nA resposta anterior:\n" + json.dumps(resposta, ensure_ascii=False))
        try:
            resposta2, modelo = ia.perguntar_json(SISTEMA, conserto, esquema(), temperatura=0.5,
                                                  transporte=transporte, gasto=gasto)
            roteiro2, problemas2 = conferir(resposta2, segundos, teto=teto)
            if roteiro2.paragrafos and len(problemas2) <= len(problemas):
                roteiro = roteiro2
        except ia.ErroDaIA:
            logger.info("o conserto do roteiro não veio; fica o primeiro")
    if not roteiro.paragrafos:
        raise SemRoteiro("A IA não devolveu o roteiro. Tente de novo.")
    roteiro.por, roteiro.pedidos, roteiro.modelo = "gemini", len(gasto), modelo
    return roteiro


__all__ = ["PALAVRAS_POR_SEGUNDO", "Roteiro", "SemRoteiro", "conferir", "escrever", "esquema",
           "montar_pedido", "palavras_alvo"]
