# Voz e bipe

**A voz** (passo 2) tem três níveis:

| Nível | O que faz |
|---|---|
| **Original** | a voz como foi gravada |
| **Limpa** | corta o grave, apara as pontas, tira o eco do cômodo e o chiado, deixa cada parte em −20 LUFS e, no fim, segura o "sss", comprime de leve e entrega em −15 LUFS |
| **Estúdio** | a limpa, mais um equalizador com brilho, a compressão em duas etapas e a voz aberta em estéreo |

Os filtros são os do FFmpeg que vem dentro do PyAV, e nada precisa ser instalado. Com
vários áudios, cada um é tratado e nivelado à parte: no vídeo de teste, cinco parágrafos
gravados com até 5 dB de diferença saíram a 1,2 dB um do outro.

**O bipe** esconde uma sílaba de cada palavra da lista (passo 2, separadas por vírgula):
a do meio, nunca a primeira, com um tom de 1 kHz e a voz zerada por baixo. A legenda e os
cartões mostram a mesma sílaba em asteriscos: "porca\*\*a", "dro\*\*".

- **O plural e o acento contam:** "porcaria" também pega "porcarias".
- **A lista vai de dica para o Whisper.** Sem ela, o modelo `small` trocava uma palavra
  pouco comum por duas parecidas, e a palavra escapava do bipe.
- **A sílaba é estimada:** o começo e o fim da palavra são medidos no áudio, e as sílabas
  são divididas pelo número de letras, com uma folga de 30 ms de cada lado. É menos
  preciso que um alinhador fonético, que não cabe num editor leve. No vídeo de teste,
  transcrito de novo depois do bipe, o Whisper não reconheceu nenhuma das seis palavras.
- **Nenhum efeito sonoro** toca em cima de um bipe.
