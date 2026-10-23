# Desempenho

Medido num MacBook com **Apple M5** (10 núcleos), num vídeo vertical 1080×1920 com
25 quadros por segundo:

| Vídeo | Resultado | Tempo total | Detalhe |
|---|---|---|---|
| 1 min 46 s | 1 min 12 s (34 s de pausas cortadas) | **51 s** | ~11 s transcrevendo (`small`) e ~40 s desenhando e gravando |
| o mesmo, em 720p | 1 min 12 s | 28 s | já transcrito |
| 27 s | 18 s | 12 s | |
| o mesmo, a 60 quadros por segundo (o preset de gameplay) | 18 s | 20 s | já transcrito; a 25 quadros, 10 s |

O pico de memória ficou em 1,3 GB. Num computador mais modesto, conte com mais tempo.

**Na montagem**, o tempo depende de quem vai por cima. Medido no mesmo M5, com a fala de
27 s e uma gravação de tela de 15 s no fundo, com outros programas abertos:

| Por cima | Quadro | Tempo |
|---|---|---|
| a pessoa, recortada pelo MODNet | deitado, 1280×720 | 49 s |
| a pessoa, recortada pelo MODNet | em pé, 720×1280 | 48 s |
| a pessoa já sem fundo (MOV ProRes 4444) | quadrado, 720×720 | 14 s |
| um personagem em GIF, com a narração à parte | em pé, 720×1280 | 10 s |

O MODNet recorta o vídeo da pessoa inteiro, quadro a quadro: é ele que custa. Exportar o
vídeo já sem fundo (WebM VP9 ou MOV ProRes 4444, no CapCut ou no Premiere) evita esse
tempo.

Para ir mais rápido:

- use a prévia de 15 s para acertar o estilo;
- grave em 720p;
- troque o modelo para `base`.

Editar de novo o mesmo vídeo pula a transcrição. Os tempos da voz sintetizada estão em
[Minha voz](./minha-voz).
