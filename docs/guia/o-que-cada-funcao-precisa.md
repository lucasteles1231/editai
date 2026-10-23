# O que cada função precisa

O editor instala o que todo vídeo usa. O resto só entra quando você usa: é baixado na
primeira vez, instalado à parte por um botão, ou é um serviço na internet, com uma chave
sua. As medidas são de um MacBook com Apple M5 (10 núcleos, 16 GB).

| Função | Obrigatória | Como entra | Disco | Memória (pico) | Onde roda | Internet | Tempo no M5 |
|---|---|---|---|---|---|---|---|
| **O editor:** a página, os cortes, as legendas, o zoom, os adesivos, os ícones, os sons, os presets, a montagem, a janela, os cartões, a voz limpa e de estúdio, os efeitos na voz, o bipe, a biblioteca de cenas e a exportação | sim | vem na instalação | ~340 MB, com o Python e o uv | 1,3 GB num vídeo falado de 1 min 46 s; 1,7 GB numa notícia de 49 s em 1080×1920 | processador, em todos os núcleos | só para instalar | 51 s para o vídeo de 1 min 46 s; 116 s para a notícia |
| **A transcrição** (Whisper) | sim, para o vídeo com fala | baixa no primeiro uso | 464 MB no `small` (de 75 MB no `tiny` a 1,5 GB no `medium`) | 1,3 GB no `small`; 2,4 GB no `medium` | processador | só na primeira vez | 40 s de fala em 10 s no `small` e em 29 s no `medium` |
| **O recorte da pessoa** (MODNet), na thumbnail e na montagem | não | baixa no primeiro uso | 26 MB | | processador | só na primeira vez | ~0,07 s por quadro |
| **O Gemini:** ideias de thumbnail, roteiro, cartões, destaques e matriz | não | serviço, com uma chave grátis | | | nos servidores do Google | sim | segundos por pedido |
| **O fundo gerado** pelo Gemini | não | serviço pago, uns US$ 0,04 por imagem | | | nos servidores do Google | sim | |
| **As fotos do Pexels**, na thumbnail | não | serviço, com uma chave grátis | | | nos servidores do Pexels | sim | |
| **O avatar:** o criador, os 36 quadros e o avatar na montagem e na thumbnail | não | vem na instalação | ~900 KB de partes | | os quadros, no navegador; a montagem, no processador | não | menos de 3 s para os 36 quadros |
| **O avatar pela foto** (o Gemini escolhe as partes) | não | serviço, com a chave grátis | | | nos servidores do Google | sim | segundos |
| **Os 4 sons do tema Notícia** sem licença livre | não | baixam no primeiro uso | ~0,6 MB | | | só na primeira vez; sem ela, toca um parecido | |
| **Minha voz** (Qwen3-TTS) | não | instalação à parte, por um botão | ~3,5 GB: o ambiente (1,2 GB) e o modelo (2,3 GB) | 5,4 GB na placa do Mac (memória unificada); 7,5 GB só no processador | chip Apple ou placa NVIDIA, de preferência; também só no processador, mais devagar | só para instalar | de 1,4 a 1,8 vez a duração da fala na placa; ~3,4 vezes só no processador |
| **O navegador**, para a página | sim | já está no computador | | | | não | |

- **O mínimo:** o editor e o Whisper `small`, uns 0,8 GB de disco. Num computador com 8
  GB de memória, sobra.
- **Com a Minha voz:** mais uns 3,5 GB de disco e, de preferência, um Mac com chip Apple
  ou um PC com placa NVIDIA. O pico medido foi de 5,4 GB: num computador de 8 GB, feche
  os outros programas antes de narrar. Só no processador, ela pede 16 GB.
- **Onde foi testado:** os [testes](https://github.com/lucasteles1231/editai/actions/workflows/testes.yml) rodam em Windows, macOS e Linux, e
  a página, no Chromium, no Firefox e no WebKit. A Minha voz foi medida só no Mac: no
  Windows, a instalação escolhe o PyTorch com CUDA quando há placa NVIDIA, mas ainda não
  foi experimentada num PC de verdade.
- **Os tempos** são do M5. Num computador mais modesto, conte com mais; veja
  [Desempenho](./desempenho).
