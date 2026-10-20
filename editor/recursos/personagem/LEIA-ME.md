# O personagem: o padrão e as partes do avatar

O avatar do Editai (`editor/avatar.py` e `web/src/avatar/`) segue o padrão do apresentador do
projeto anterior (o `um projeto anterior`, de 12 a 16/10/2026).

| Arquivo | O quê |
|---|---|
| `padrao.json` | o quadro (900 × 900, grade de 150, ampliada 6 vezes sem suavizar), as camadas, as 12 poses (o gesto, a expressão e quando usar cada uma), as 3 bocas, a regra da boca pelas sílabas, a cena e a capa |
| `catalogo.json` | o que se escolhe em cada categoria (em português para a página e em inglês para o Gemini), as cores sugeridas, o avatar padrão e o hash de cada parte |
| `partes/` | as partes vetorizadas, com os tons separados por espaço de cor (`pele`, `cabelo-sombra`, `roupa-luz`…) |

As partes, o padrão e o catálogo são uma cópia do repositório público
[editai-personagens](https://github.com/lucasteles1231/editai-personagens), do commit
`a1a94e9` (20/10/2026), em domínio público (CC0). Lá estão também o manequim e as ferramentas
que geram e vetorizam a biblioteca. Para trazer uma versão nova, copie `partes/`, `padrao.json`
e `catalogo.json` de lá e rode `uv run pytest tests/test_avatar.py`: o primeiro teste confere o
hash de cada parte contra o catálogo.

**De onde vem cada regra:**

- **As 12 poses e quando usar cada uma:** o `documento.py` de um projeto anterior.
- **As 3 bocas:** o `meia_boca.py`. A meia não é gerada: ela é desenhada a partir da aberta,
  com a mesma largura e metade da altura. Nas poses em que a boca fechada já é aberta (o "o"
  do surpreso e a risada), a meia e a aberta continuam a da pose.
- **A boca pelas sílabas:** o `boca_por_quadro` (`palco/montagem.py`).
  - Os picos saem do envelope de 25 ms, a cada 10 ms, com pelo menos 130 ms entre eles.
  - A boca abre um quadro antes de cada pico, sempre pela meia, e fica aberta de 2 a 6 quadros.
  - A sílaba fraca, abaixo de 0,85 da mediana das vizinhas, abre só até a meia.
  - O Editai não tem o scipy, então os picos são feitos em numpy (`avatar._picos`), e foram
    conferidos contra o `find_peaks` numa fala real: 148 de 148 iguais.
- **A pose de cada frase:** num projeto anterior, ela vinha do roteiro. Aqui, a regra é local (`avatar.pose_da_fala`):
  - pergunta → pensando;
  - "você" → apontando para quem assiste;
  - "eu" → a mão no peito;
  - número ou "!" → o dedo para cima;
  - "olha aqui" → apontando para o lado;
  - risada → rindo;
  - no resto, explicando e neutro, alternados.
- **O espelho:** do lado direito da tela, o avatar é espelhado, e a pose "apontando para o
  lado" aponta para o meio.
- **O pulinho ao trocar de pose:** de 0,95 a 1 em 0,16 s.
