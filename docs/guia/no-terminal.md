# No terminal

A interface é o jeito mais fácil, mas tudo também funciona direto no terminal. O comando
é `editai` (o `editai`, nome de antes, continua funcionando):

```bash
editai meu-video.mp4
```

O resultado sai ao lado do original, como `meu-video-editado.mp4`, junto com o
`.plano.json`, que guarda tudo o que foi decidido. Alguns exemplos:

```bash
editai aula.mov --srt --vtt                       # também grava as legendas à parte
editai video.mp4 --previa 15                      # só os primeiros 15 s, para testar
editai video.mp4 --formato webm --resolucao 720p  # WebM (VP9) em 720p
editai jogo.mp4 --preset gameplay                 # o preset de gameplay (veja --presets)
editai jogo.mp4 --preset gameplay --ritmo 1.2     # o preset, com o ritmo um pouco menor
editai --preset vlog --ritmo 0.9 --salvar-preset "Meu vlog"   # um preset seu
editai video.mp4 --preset meu-vlog                # e usá-lo
editai video.mp4 --tema-dos-sons humor --som-nos-cortes
editai video.mp4 --sem-zoom --sem-sons            # sem zoom e sem efeitos sonoros
editai eu.mp4 --fundo tela.mp4 --quadro vertical  # você por cima da tela gravada, em pé
editai --fundo jogo.mp4 --personagem boneco.gif --audio narracao.m4a
editai --fundo jogo.mp4 --avatar "Ana" --audio narracao.m4a   # o seu avatar, falando
editai --gerar-matriz cenas/ --assunto "trailers do GTA 6"   # escreve cenas/cenas.json
editai --cenas imovel/ --matriz imovel/cenas.json --audio imovel/tour-1.mp4 imovel/tour-2.mp4 \
       --preset imoveis               # fotos e vídeos de um imóvel, o som de dois vídeos dela
editai --cenas cenas/ --matriz cenas/cenas.json --audio p1.m4a p2.m4a p3.m4a \
       --personagem boneco.gif --preset noticia --quadro vertical
editai video.mp4 --voz limpa --bipe "palavra, outra"  # voz limpa e bipe na lista
editai video.mp4 --efeito-na-voz esquilo           # a voz de esquilo (veja --efeitos)
editai video.mp4 --efeito-na-voz "tom=-5,sala=40"  # ou os ajustes, do seu jeito
editai --instalar-voz                             # a voz sintetizada (Minha voz), ~3,5 GB
editai --atualizar                                # a última versão publicada, por cima
editai --desinstalar                              # tira o Editai do computador (pergunta antes)
editai --criar-voz "Ana"                          # mostra o texto a ler
editai --criar-voz "Ana" --gravacao leitura.m4a   # confere a leitura e salva a voz
editai --cenas cenas/ --matriz cenas/cenas.json --minha-voz ana --roteiro roteiro.txt \
       --preset noticia --quadro vertical         # a notícia, narrada com a sua voz
editai eu.mp4 --fundo aula.mp4 --fala fundo        # o som vem da aula, e não da câmera
editai talk.mp4 --idioma en --modelo medium       # fala em inglês, modelo maior
editai video.mp4 -o final.mov --codec prores      # ProRes, para levar a outro editor
editai --formatos                                 # o que este computador grava
```

<details>
<summary><b>Todas as opções</b></summary>

| Opção | O que faz | Padrão |
|---|---|---|
| `-o`, `--saida` | onde gravar | `<nome>-editado.<ext>` |
| `--preset` | o ponto de partida: `padrao`, `gameplay`, `vlog`, `review`, `tecnico`, `humor`, `motivacional`, `podcast`, `aula`, `imoveis`, `noticia` ou um seu | `padrao` |
| `--presets` | mostra os presets, os prontos e os seus | |
| `--salvar-preset NOME` | salva como um preset seu o `--preset` de partida com as flags de edição e de saída por cima (o mesmo nome substitui) | |
| `--frase TEXTO` | com `--salvar-preset`: a frase que descreve o preset | |
| `--sem-cortes` | não corta os silêncios | |
| `--sem-zoom` | sem zoom de ênfase | |
| `--sem-adesivos` | sem palavras que saltam | |
| `--sem-icones` | sem ícones automáticos | |
| `--sem-sons` | sem efeitos sonoros | |
| `--pausa S` | a maior pausa que fica sem corte, em segundos | `0.45` |
| `--respiro S` | o silêncio que fica no lugar de uma pausa cortada | `0.15` |
| `--ritmo N` | de `0.5` a `2`: quantos efeitos entram, e o quanto perto | `1` |
| `--zoom N` | o nível do zoom (`1.12` = 12%) | `1.12` |
| `--empurrao N` | o zoom rápido de cada adesivo (`0.06` = 6%; `0` desliga) | `0.06` |
| `--ancora X,Y` | o centro do zoom, de 0 a 1 | `0.5,0.4` |
| `--tamanho-legenda N` | `0.8` menor, `1.25` maior | `1.0` |
| `--caracteres-por-linha N` | de 10 a 42: a largura da legenda | 18 em pé, 32 deitado |
| `--tema-dos-sons` | `padrao`, `suave`, `gameplay`, `review`, `tecnico`, `humor` ou `epico` | `padrao` |
| `--volume-dos-sons N` | de `0.3` a `1.5` | `1` |
| `--som-nos-cortes` | um clique baixo em cada corte | |
| `--sem-sons-por-palavra` | sem o som de cada palavra ("dinheiro" e as moedas) | |
| `--animacoes` | os cartões animados, escritos pelo Gemini | |
| `--legenda` | `classica` ou `destaques` | `classica` |
| `--texto-falado ARQUIVO` | o texto que você falou (.txt): a legenda pega a grafia dele | |
| `--voz` | `original`, `limpa` ou `estudio` | `original` |
| `--efeito-na-voz` | um efeito pronto ou seu (veja `--efeitos`), ou os ajustes: `"tom=9,eco=30"`; `nenhum` tira o do preset | |
| `--efeitos` | mostra os efeitos na voz, os prontos e os seus, com os ajustes | |
| `--bipe PALAVRAS` | as palavras proibidas, separadas por vírgula | |
| `--fundo` | a montagem: o vídeo de fundo, sem pessoa | |
| `--cenas PASTA` | a montagem com a biblioteca de cenas: a pasta dos clipes | |
| `--matriz ARQUIVO` | a matriz da biblioteca (o `cenas.json`) | |
| `--gerar-matriz PASTA` | escreve o `cenas.json` de uma pasta de clipes (o Gemini descreve; sem ele, um rascunho) | |
| `--assunto TEXTO` | com `--gerar-matriz`: do que são as cenas, para reconhecer personagens | |
| `--janela`, `--sem-janela` | a cena numa janela 16:9 com câmera | sem |
| `--pessoa` | o vídeo de você falando, por cima do fundo | o vídeo do argumento |
| `--personagem` | um GIF, PNG animado ou WebP, em loop por cima | |
| `--avatar NOME` | o seu avatar (criado na página), por cima: a pose de cada frase e a boca nas sílabas | |
| `--audio` | um ou vários áudios separados (a narração gravada à parte), tocados em ordem | |
| `--fala` | de onde vem o áudio: `fundo`, `pessoa` ou `audio` | o `--audio`; senão a pessoa, se tiver som; senão o fundo |
| `--instalar-voz` | instala a voz sintetizada (Minha voz), num ambiente à parte | |
| `--atualizar` | instala a última versão publicada por cima desta ([Atualizar](./instalacao-em-detalhe#atualizar)) | |
| `--criar-atalho` | cria o atalho "Editai": Aplicativos no macOS, menu Iniciar e Área de Trabalho no Windows, menu de aplicativos no Linux | |
| `--desinstalar-voz` | apaga o motor da voz sintetizada (as vozes gravadas ficam) | |
| `--desinstalar` | tira o Editai do computador: mostra tudo, pergunta à parte pelos modelos e pelos vídeos e pede "sim" ([Desinstalar](./instalacao-em-detalhe#desinstalar)) | |
| `--sim` | com `--desinstalar` ou `--desinstalar-voz`: não pergunta nada | |
| `--com-modelos`, `--com-videos` | com `--desinstalar`: apaga também os modelos do Whisper e do MODNet, e os vídeos editados | ficam |
| `--criar-voz NOME` | sem `--gravacao`, mostra o texto a ler; com ela, confere a leitura e salva a voz | |
| `--gravacao ARQUIVO` | com `--criar-voz`: a leitura inteira, gravada num arquivo | |
| `--vozes` | mostra as vozes salvas | |
| `--minha-voz NOME` | narra o `--roteiro` com a voz salva; com `--cenas` ou `--fundo`, a narração vira o áudio da montagem (sozinho, grava `<roteiro>-narrado.wav`) | |
| `--roteiro ARQUIVO` | o texto a narrar (`.txt`), com uma linha em branco entre os parágrafos | |
| `--pronuncia LISTA` | como o motor lê uma palavra: `"PEGI=pégui; GTA=gê tê á"` (a legenda não muda) | a lista salva com a voz |
| `--recorte` | `transparente` (o vídeo já vem sem fundo) ou `modnet` | detectado no arquivo |
| `--quadro` | `fundo`, `vertical`, `horizontal` ou `quadrado` | `fundo` |
| `--parada`, `--mover` | quem está por cima fica parado, ou muda de lugar | muda |
| `--manter-fundo-do-personagem` | não tira o fundo de cor única do personagem | |
| `--idioma` | o idioma da fala (`pt`, `en`, `es`…) | `pt` |
| `--modelo` | `tiny`, `base`, `small` ou `medium` | `small` |
| `--previa S` | edita só os primeiros segundos | |
| `--formato` | `mp4`, `mov`, `webm`, `mkv` ou `gif` | a extensão do `-o`, ou `mp4` |
| `--codec` | `h264`, `h265`, `vp9`, `av1`, `prores` ou `gif` | o melhor do formato |
| `--resolucao` | `original`, `2160p`, `1440p`, `1080p`, `720p` ou `480p` | `original` |
| `--fps` | `original`, `24`, `30` ou `60` | `original` |
| `--qualidade` | `alta`, `equilibrada` ou `leve` | `alta` |
| `--srt`, `--vtt` | grava também a legenda à parte | |
| `--porta N` | a porta da interface | uma livre |
| `--sem-navegador` | abre a interface sem abrir o navegador | |
| `--formatos` | mostra os formatos e codecs que este computador grava | |
| `--versao` | mostra a versão do Editai e sai | |

Os padrões da tabela são os do preset `padrao`. Com `--preset`, valem os do preset
escolhido, e as flags passadas ganham dele. `editai --ajuda` mostra a mesma lista.

</details>
