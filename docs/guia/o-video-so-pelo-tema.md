# O vídeo só pelo tema

Sem vídeo, sem áudio e sem cenas: você escreve o assunto em uma frase, e o Editai faz o
resto. É o vídeo de explicação dos canais que só narram, com fotos passando por trás.

1. **O roteiro.** A IA escreve a narração a partir do tema, e você revisa antes de narrar.
2. **As fotos.** O Editai acha fotos com licença livre para cada trecho do roteiro.
3. **A voz.** Uma voz pronta (a do Gemini ou a do computador), ou a sua, narra o roteiro.
4. **A edição de sempre:** a legenda, os cortes, o zoom, os ícones, os sons e, se você
   tiver, o seu avatar por cima.

**O que precisa:** a chave grátis do Gemini, para escrever o roteiro. Pegue a sua no
[Google AI Studio](https://aistudio.google.com/apikey) e cole em **Antes de começar**, logo
abaixo do título. Sem ela, marque também **Roteiro** e escreva o texto você mesmo: o resto
funciona igual, com a voz local ou a sua.

## Na página

1. No passo 1, marque só **Tema** e escreva o assunto: "por que o céu é azul".
2. **A duração.** O padrão sai de onde o vídeo vai: 45 s nos Shorts, no TikTok e nos Reels,
   e 3 min no YouTube. Dá para escolher de 30 s a 5 min.
3. **Escrever o roteiro.** Ele aparece logo abaixo, para você revisar:
   - a voz lê exatamente esse texto;
   - cada parágrafo (separado por uma linha em branco) vira um trecho do vídeo, com a sua
     foto;
   - **Escrever de novo** troca o roteiro inteiro, com as suas mudanças.
4. **Achar as fotos**, em **A imagem**. Elas viram uma biblioteca de cenas como outra
   qualquer:
   - **Revisar as fotos** abre a tabela de sempre, para tirar uma foto ruim (marque
     "evitar") ou corrigir a descrição;
   - mudou o roteiro depois, a página avisa, e **Achar de novo** busca para o texto novo.
5. **Por cima:** o seu avatar ([Meu avatar](./meu-avatar)), se você tiver um, ou ninguém.
6. **A voz**, em **A fala**: escolha e clique em **Narrar o roteiro**. A narração vira o
   áudio do vídeo, e dela saem a legenda e os cortes.
7. **Editar vídeo.** A legenda sai com a grafia do roteiro.

**O roteiro que a IA escreve** segue as regras de um vídeo curto que segura a atenção:

- a primeira frase é o gancho (uma pergunta ou um fato que intriga), sem "você sabia" e sem
  "neste vídeo";
- as frases são curtas, de fala;
- não há número inventado: na dúvida, ela explica sem o número;
- termina com uma pergunta para quem assiste comentar.

Mesmo assim, **revise**. O que ela escreve é dela, e um fato errado num vídeo é seu.

## As fotos

**De onde vêm:**

- do **Pexels**, se você tiver a chave grátis dele (em **Antes de começar**);
- do **[Openverse](https://openverse.org/)**, sem chave, só com as licenças que deixam pôr a
  foto num vídeo sem pedir: CC0, domínio público e CC BY.

A CC BY-SA (que obrigaria o vídeo a ter a mesma licença), a "não comercial" (NC) e a "sem
derivados" (ND) ficam de fora.

**Como são escolhidas:**

1. O roteiro é partido nos trechos em que a imagem muda: os parágrafos, e os longos, nas
   frases.
2. A IA diz, num pedido só, o que mostrar em cada trecho: uma busca concreta em inglês
   ("rocket launch") e uma descrição em português. Sem a IA, a busca são as palavras do
   próprio trecho.
3. Saem a foto pequena, a repetida e a que é texto, logo, diagrama ou captura de tela.
4. Ficam 2 fotos por trecho. Um trecho sem nenhuma fica com as dos vizinhos.

**Os créditos.** As fotos ficam em `Filmes/editor-de-video/fotos/<tema>`, com o
`cenas.json` e o `creditos.txt`. **Cole as linhas do `creditos.txt` na descrição do
vídeo:** a CC BY pede o crédito, com o autor, a licença e o link. As do Pexels e as CC0 não
pedem, mas estão lá também.

**Em pé ou deitado:** para um vídeo em pé, o Pexels manda fotos em pé, e o Openverse, de
qualquer formato (as em pé com licença livre são poucas): o quadro mostra o meio delas.

## As vozes

| Voz | Onde roda | O que custa | Bom para |
|---|---|---|---|
| **As do Gemini:** Orus, Charon, Puck, Kore, Aoede e Leda | nos servidores do Google | a cota grátis da sua chave: 10 narrações por dia | a voz mais natural, sem instalar nada |
| **Faber, a local** (o [Piper](https://github.com/OHF-Voice/piper1-gpl)) | no seu computador, sem internet | uns 210 MB, instalados uma vez | sem cota, sem internet e rápida, mas com o som de voz sintética |
| **A sua** ([Minha voz](./minha-voz)) | no seu computador | uns 3,5 GB, e a gravação de uns 2 minutos | o canal com a sua voz |

- **A voz do Gemini** narra o roteiro inteiro num pedido só: 1 das 10 narrações do dia. A
  página mostra quantas sobram. A cota volta à meia-noite em UTC (às 21h em Brasília), e a
  mesma narração pedida de novo sai guardada, sem gastar.
- **A voz local** é instalada pelo botão que aparece quando você a escolhe (ou com
  `editai --instalar-voz-local`). Ela fica num ambiente à parte, como a Minha voz.
- **A pronúncia** (siglas e nomes estrangeiros: `PEGI = pégui`) vale para todas. Na sua
  voz, ela fica salva com a voz; nas prontas, não fica.

## No terminal

```bash
editai --tema "Por que o céu é azul"                     # escreve, narra, acha as fotos e monta
editai --tema "Por que o céu é azul" --duracao 60 --narrador gemini:Kore
editai --tema "Por que o céu é azul" --narrador local    # a voz do computador
editai --tema "Por que o céu é azul" --roteiro roteiro.txt --narrador ana   # o seu roteiro, a sua voz
editai --instalar-voz-local                              # a voz local, uns 210 MB
```

No terminal, tudo sai de uma vez, sem a revisão: o roteiro aparece na tela e fica no
`roteiro.txt`, ao lado das fotos. Para revisar antes, escreva o roteiro (ou corrija o
`roteiro.txt`) e rode de novo com `--roteiro`. Sem `--quadro`, o vídeo sai em pé (9:16), ao
lado da pasta das fotos: `Filmes/editor-de-video/fotos/<tema>-editado.mp4`. Todas as opções
estão em [No terminal](./no-terminal).

## Quanto tempo leva

Medido num MacBook M5, em 25/10/2026, com um vídeo de uns 40 s:

| Etapa | Tempo |
|---|---|
| o roteiro | de 30 s a 2 min: o modelo principal do Gemini pensa antes de escrever |
| a voz do Gemini | uns 20 s |
| a voz local | 1 a 2 s |
| as fotos | uns 15 s com a chave do Pexels; sem ela, uns 5 s a mais por trecho |
| a edição | 1 min no preset padrão; mais no Notícia, que pede os cartões ao Gemini |

Com a voz local, o vídeo inteiro saiu em pouco mais de 1 minuto. Num dia em que o modelo
principal do Gemini está sobrecarregado, cada pedido de texto pode levar uns 2 minutos antes
de o editor passar ao próximo modelo da escada.

## Quantos pedidos ao Gemini

Um vídeo de 45 s, só pelo tema, com a voz do Gemini:

| Pedido | Quantos |
|---|---|
| o roteiro | 1 (e mais 1, se o primeiro vier fora do tamanho) |
| as buscas das fotos | 1, no modelo leve, que tem a cota dele |
| a narração | 1 das 10 do dia |
| a escolha das fotos de cada trecho, os cartões e os destaques, como em todo vídeo | 1 (e mais 1, se a resposta precisar de conserto) |

A cota grátis de texto é contada por modelo e por dia, e o editor desce para o próximo
modelo quando um esgota. Na prática, a voz é o limite: 10 vídeos por dia com a do Gemini, e
sem limite com a local ou a sua. O que vai para o Google em cada
pedido está em [Segurança e privacidade](./seguranca-e-privacidade).
