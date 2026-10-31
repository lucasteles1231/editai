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

**O ruído do fundo** (passo 2, ao lado da voz) sai pelo DeepFilterNet3, um modelo que roda no
seu computador: o ventilador, o ar-condicionado, a rua, o teclado e o chiado do microfone.

| Escolha | O que faz |
|---|---|
| **Auto** (o padrão) | mede o fundo e só limpa o ruído **constante** (o ventilador, o ar-condicionado, o chiado, o ronco da rua): com mais de 30 dB de folga entre a voz e o fundo, não mexe; de 15 a 30 dB, limpa de leve; abaixo de 15 dB, limpa tudo. Música, som de jogo, teclado e vozes ao fundo variam, e ficam |
| **Leve** | tira até 12 dB de todo ruído, sempre, inclusive o teclado e as vozes ao fundo: a voz fica mais natural |
| **Forte** | tira todo o ruído que achar, sempre |
| **Não** | a voz fica com o fundo como veio |

- **Na primeira vez,** o editor pede o seu ok para baixar o modelo (13 MB). Sem ele, a voz
  segue como veio, e o resultado avisa.
- **Por que ele:** na prova, com a fala misturada a ventilador, teclado, ruído de fundo e outras
  vozes, de 0 a 20 dB, ele melhorou a fala de 6 a 18 dB, e até as outras vozes de fundo
  baixaram um pouco. Ele limpa 1 min de áudio em uns 5 s num Mac M5. O redutor de antes (que a
  voz limpa e a de estúdio usam sem ele) melhorava no máximo 3 dB, e piorava as vozes de fundo.
- **A voz fica no tempo da boca:** o modelo devolve a voz 32 ms atrasada, e o editor põe de
  volta no lugar.
- **Por que o Auto só limpa o fundo constante:** o modelo guarda só a voz, e tiraria junto a
  música e o som do jogo. Nas medidas, o ventilador varia uns 1 dB entre os trechos mais
  quietos, e a música, o teclado e as vozes, de 3 a 20 dB. Num gameplay ou num vlog com música, o
  Auto deixa o som como veio; o **Leve** e o **Forte** limpam tudo, inclusive a música.
- **Uma gravação que já veio limpa** (com silêncio digital entre as falas, de um app que corta o
  ruído) não passa por ele no Auto.
- **No terminal:** `--ruido auto|leve|forte|nao`.

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
