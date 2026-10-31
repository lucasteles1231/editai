# O vídeo só pelo tema

Sem vídeo, sem áudio e sem cenas: você escreve o assunto em uma frase, e o Editai faz o
resto. É o vídeo de explicação dos canais que só narram, com fotos passando por trás.

1. **O roteiro.** A IA escreve a narração a partir do tema, e você revisa antes de narrar.
2. **As fotos.** O Editai acha fotos com licença livre para cada trecho do roteiro, e o
   auditor fica com as que mostram o que o trecho diz.
3. **A voz.** Uma voz pronta (a do Gemini ou a do computador), ou a sua, narra o roteiro.
4. **A edição de sempre:** a legenda, os cortes, o zoom, os ícones, os sons e, se você
   tiver, o seu avatar por cima.

**O que precisa:** uma IA, para escrever o roteiro. Pode ser:
- **a IA local** ([A IA no seu computador](./a-ia-no-seu-computador)), sem internet e sem
  chave;
- **o Gemini**, com a chave grátis do [Google AI Studio](https://aistudio.google.com/apikey).

As duas ficam no cartão **A IA**, em **Antes de começar**, logo abaixo do título. Sem
nenhuma, marque também **Roteiro** e escreva o texto você mesmo: o resto funciona igual, com
a voz local ou a sua.

## Na página

1. No passo 1, marque só **Tema** e escreva o assunto: "por que o céu é azul".
2. **A duração** é a de **Quanto tempo?**, no fim do passo 1 ([veja](./como-usar#quanto-tempo)).
   No **Auto**, a IA escreve no tamanho que o assunto pede, até o limite da plataforma (3 min
   no Shorts e no Reels). Com um tempo escolhido (15 s, 30 s, 1 min…), ela escreve para ele.
3. **Escrever o roteiro.** Para um assunto de agora (uma notícia da semana), ligue antes
   **Pesquisar na internet** ([veja](#pesquisar-na-internet)). O roteiro aparece logo abaixo,
   para você revisar:
   - a voz lê exatamente esse texto;
   - cada parágrafo (separado por uma linha em branco) vira um trecho do vídeo, com a sua
     foto;
   - **Escrever de novo** troca o roteiro inteiro, com as suas mudanças.
4. **Achar as fotos**, em **A imagem**. Com **Conferir as fotos** ligado (o padrão), o
   [auditor](#o-auditor) escolhe as que mostram cada trecho. Elas viram uma biblioteca de
   cenas como outra qualquer:
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

## Pesquisar na internet

O que a IA sabe tem data de corte: sem pesquisa, uma notícia da semana sai velha, ou
inventada. Com **Pesquisar na internet** ligado, o roteiro sai do que a internet traz hoje.

1. **O editor busca o tema** nas notícias e na Wikipédia. Essa primeira busca é dele, e não
   da IA: medido em 26/10/2026, metade dos modelos não pediu nenhuma busca sozinha.
2. **A IA busca e lê o que mais quiser,** até 4 buscas e 3 páginas, e anota os fatos, cada um
   com o número da fonte.
3. **O roteiro é escrito só com essas notas.** As fontes aparecem embaixo dele, com os links,
   para você conferir antes de narrar.

**As fontes,** todas grátis e sem chave:
- **as notícias:** o RSS do Bing Notícias e, se ele não responder, o do Google Notícias;
- **os fatos:** a Wikipédia.

Nenhum dos dois RSS tem termos de uso publicados para esse uso.

**O que sai do computador:** o tema e as buscas que a IA fizer vão para essas fontes, e as
páginas lidas são baixadas. Com a IA local, o resto continua no computador.

**No terminal:** `--pesquisar`, com `--tema`. As fontes aparecem embaixo do roteiro.

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
   ("rocket launch"), uma busca de reserva, mais ampla ("rocket"), e uma descrição em
   português. Sem a IA, a busca são as palavras do próprio trecho.
3. Saem a foto pequena, a repetida e a que é texto, logo, diagrama ou captura de tela.
4. O auditor dá uma nota a cada candidata, e ficam as 2 que mais mostram o trecho. Um trecho
   sem nenhuma fica com as dos vizinhos.
5. **No vídeo, cada foto entra no trecho dela:** a narração é casada palavra a palavra com o
   roteiro, sem pedido à IA. Isso vale também quando o **Quanto tempo?** tira frases.

**Os créditos.** As fotos ficam em `Filmes/editor-de-video/fotos/<tema>`, com o
`cenas.json` e o `creditos.txt`. **Cole as linhas do `creditos.txt` na descrição do
vídeo:** a CC BY pede o crédito, com o autor, a licença e o link. As do Pexels e as CC0 não
pedem, mas estão lá também.

**Em pé ou deitado:** para um vídeo em pé, o Pexels manda fotos em pé, e o Openverse, de
qualquer formato (as em pé com licença livre são poucas): o quadro mostra o meio delas.

## O auditor

O banco de fotos devolve de tudo para uma busca. Sem o auditor, ficavam as 2 primeiras, e
num vídeo sobre o GPS entraram uma aranha no lugar de um satélite, o mar no lugar de "quatro
satélites" e ciclistas no lugar de "um satélite em movimento".

**Como funciona:**

1. Das fotos de cada busca, as 12 primeiras ganham uma nota. Ela diz o quanto a foto mostra
   a descrição do trecho.
2. Ficam as 2 de nota mais alta, se passarem do mínimo.
3. Uma foto quase igual a outra já escolhida fica de fora, no mesmo trecho ou no vídeo
   inteiro: o banco de fotos devolve várias da mesma sessão.
4. Sem 2 fotos boas, vem a busca de reserva. Se nem ela trouxer, as dos vizinhos cobrem o
   trecho.

**O modelo** é o [SigLIP 2](https://huggingface.co/google/siglip2-base-patch16-224), do
Google, que entende a descrição em português. Ele roda no seu computador, sem chave e sem
mandar nada para fora:

- **na primeira vez,** baixa uns 410 MB do Hugging Face, conferidos pelo SHA-256;
- **a memória:** o editor usa uns 370 MB enquanto confere. A descrição de cada trecho sai
  num processo à parte, que ocupa 1,1 GB por menos de 1 s e devolve tudo ao sair.

No vídeo do GPS (23 trechos), ele olhou 278 fotos, 66 delas não mostravam o trecho, e
nenhum trecho ficou sem as suas 2.

**Para desligar,** desmarque **Conferir as fotos**, ou use `--sem-auditor` no terminal:
ficam as primeiras de cada busca, como antes. Sem internet na primeira vez, ele também fica
de fora, e a página avisa.

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
editai --tema "Por que o céu é azul" --duracao 60 --narrador gemini:Kore   # 1 min
editai --tema "Por que o céu é azul" --narrador local    # a voz do computador
editai --tema "Por que o céu é azul" --roteiro roteiro.txt --narrador ana   # o seu roteiro, a sua voz
editai --instalar-voz-local                              # a voz local, uns 210 MB
editai --tema "Por que o céu é azul" --sem-auditor       # as primeiras fotos de cada busca
editai --tema "GTA 6: a pré-venda" --pesquisar           # com o que a internet traz hoje
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
| as fotos | uns 20 s com a chave do Pexels, já com o auditor (7 trechos); sem a chave, uns 5 s a mais por trecho; na primeira vez, mais o download do auditor |
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
| os cartões e os destaques, se estiverem ligados | 1 (e mais 1, se a resposta precisar de conserto) |

A cota grátis de texto é contada por modelo e por dia, e o editor desce para o próximo
modelo quando um esgota. Na prática, a voz é o limite: 10 vídeos por dia com a do Gemini, e
sem limite com a local ou a sua. O que vai para o Google em cada
pedido está em [Segurança e privacidade](./seguranca-e-privacidade).
