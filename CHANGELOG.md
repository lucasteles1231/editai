# Versões

O que mudou em cada versão do Editai. Cada versão publicada tem os instaladores e o pacote
na [página dela no GitHub](https://github.com/lucasteles1231/editai/releases), e a mais nova
está sempre no [site](https://lucasteles1231.github.io/editai/baixar).

Os números seguem o [versionamento semântico](https://semver.org/lang/pt-BR/): o último muda
nas correções, o do meio nas novidades e o primeiro quando algo deixa de funcionar como antes.

## [0.6.0] — 31/10/2026

### Novidades

- **A IA no seu computador.** O Qwen3.5-4B, um modelo aberto, faz no computador o que o
  Gemini faz:
  - o roteiro, as cenas e os cartões;
  - a matriz das cenas;
  - o avatar pela foto e as ideias de capa.

  Ele roda sem internet e sem chave, e nada sai do computador.
  - Instale em **Antes de começar**, no cartão **A IA** (uns 3,5 GB), ou com
    `editai --instalar-ia`.
  - No mesmo cartão, escolha quem responde: a **automática** (o Gemini, se houver a chave, e
    senão a local), o Gemini ou a IA local. No terminal: `--ia`.
  - Se a escolhida falhar, o editor avisa e para, sem trocar de IA sozinho.
  - Antes de escolher o modelo, quatro deles foram medidos contra o Gemini nas tarefas do
    editor. No texto, a IA local fica atrás do Gemini, e vale revisar os fatos.

  [Veja como](https://lucasteles1231.github.io/editai/guia/a-ia-no-seu-computador).
- **Pesquisar na internet.** No vídeo pelo tema, o roteiro de um assunto de agora sai do que
  a internet traz hoje.
  - As fontes são as notícias (o RSS do Bing e do Google Notícias) e a Wikipédia, grátis e
    sem chave.
  - A IA busca e lê o que precisar, e escreve só com o que acha.
  - As fontes aparecem embaixo do roteiro, com os links, para você conferir.
  - No terminal: `--pesquisar`.

  [Veja como](https://lucasteles1231.github.io/editai/guia/o-video-so-pelo-tema#pesquisar-na-internet).

## [0.5.1] — 26/10/2026

### Correções

- **A matriz das cenas não troca mais as descrições.** O Gemini via 12 cenas por pedido e às
  vezes dava a uma cena a descrição da vizinha: nas 19 fotos de um imóvel, acertou 10. Agora
  ele vê 4 por pedido e acertou as 19. Uma biblioteca grande gasta uns 3 vezes mais pedidos
  da cota grátis (128 cenas: uns 32), e o editor passa ao próximo modelo quando a cota de um
  acaba.

## [0.5.0] — 26/10/2026

### Novidades

- **O auditor das fotos.** No vídeo só pelo tema, as fotos de cada busca ganham uma nota
  pelo que mostram, e ficam as 2 que mais mostram o trecho. Antes, ficavam as 2 primeiras
  da busca, e entravam fotos sem nada a ver, como uma aranha no lugar de um satélite.
  - Ele roda no seu computador, com o SigLIP 2 do Google, que baixa uns 410 MB na primeira
    vez.
  - Uma foto quase igual a outra já escolhida fica de fora.
  - Sem 2 fotos boas, vem uma busca de reserva, mais ampla.
  - Para desligar, desmarque **Conferir as fotos**. No terminal, use `--sem-auditor`.

  [Veja como](https://lucasteles1231.github.io/editai/guia/o-video-so-pelo-tema#o-auditor).

### Correções

- **No vídeo pelo tema, cada foto entra no trecho dela.** Antes, a IA distribuía as fotos
  pela fala e, sem poder repetir nenhuma, punha a foto do começo no meio do vídeo. Agora a
  narração é casada com o roteiro, palavra a palavra, e as fotos seguem os trechos, sem
  pedido à IA.

### Melhorias

- **As fotos chegam mais rápido:** as buscas de todos os trechos correm juntas, e a espera
  entre os pedidos ficou só para o Openverse, que limita o anônimo a 20 por minuto.

## [0.4.0] — 25/10/2026

### Novidades

- **Quanto tempo?** No fim do passo 1, escolha quanto o vídeo deve durar: Auto, 15 s, 20 s…
  10 min, ou Tudo.
  - Se a fala passar do tempo, a IA escolhe as frases que ficam, inteiras e na ordem, e o
    editor corta o resto.
  - No Auto, só sai o que passar do limite da plataforma marcada (3 min no Shorts e no Reels,
    10 min no TikTok).
  - O resultado mostra o que ficou de fora, e **Refazer com tudo** edita sem tirar nada.
  - No vídeo pelo tema, a escolha é o tamanho do roteiro, e no Auto ele sai no tamanho que o
    assunto pede.

  No terminal: `--duracao auto|tudo|SEGUNDOS`. [Veja como](https://lucasteles1231.github.io/editai/guia/como-usar#quanto-tempo).

## [0.3.0] — 25/10/2026

### Novidades

- **Um vídeo longo vira a biblioteca de cenas.** No campo das cenas, solte o vídeo inteiro:
  o Editai acha os cortes, grava cada cena numa pasta em `Filmes/editor-de-video/cenas` e
  escreve o `cenas.json`, que você revisa na tabela de sempre. A tomada comprida vira
  pedaços de uns 2 s, e só um pedaço de cada tomada vai ao Gemini. No terminal:
  `editai --separar-cenas VIDEO`.
- **O vídeo só pelo tema.** Marque só **Tema** e escreva o assunto:
  - a IA escreve o roteiro no tamanho certo (45 s nos Shorts, 3 min no YouTube), e você
    revisa antes de narrar;
  - o Editai acha 2 fotos para cada trecho, no Openverse (só CC0, domínio público e CC BY)
    e, com a chave, no Pexels, com os créditos num `creditos.txt`;
  - uma voz narra, e a edição é a de sempre.

  No terminal: `editai --tema "…"`. [Veja como](https://lucasteles1231.github.io/editai/guia/o-video-so-pelo-tema).
- **As vozes prontas,** ao lado da sua voz gravada:
  - as 6 do Gemini, na cota grátis da sua chave (10 narrações por dia, com as que sobram à
    vista);
  - a Faber, local: o Piper, num ambiente à parte (uns 210 MB), sem internet e sem cota.

  No terminal: `--narrador` e `--instalar-voz-local`.

### Mudanças

- **Sem vídeo e sem cenas, a imagem são as fotos achadas** pelo roteiro (antes, a página
  dizia "na próxima versão").
- **O tema com as cenas, sem áudio,** agora vira um roteiro escrito pela IA e narrado por
  cima das cenas. O som das próprias cenas continua em **Ajustar as camadas**.

## [0.2.0] — 23/10/2026

### Novidades

- **O instalador para macOS, Windows e Linux.** Um comando, ou um arquivo para abrir com dois
  cliques, instala tudo e cria o atalho **Editai** (em Aplicativos no macOS, no menu Iniciar e
  na Área de Trabalho no Windows, e no menu de aplicativos no Linux).
- **O site**, com a documentação completa, os downloads e esta lista de versões.
- **O aviso de versão nova.** Uma vez por dia, o Editai confere no GitHub se saiu uma versão
  nova e avisa na página. `editai --atualizar` instala a nova por cima. Dá para desligar
  o aviso.
- **`editai --desinstalar`** tira o Editai do computador. Ele mostra tudo antes, pergunta à
  parte pelos modelos e pelos vídeos editados e só apaga depois de você digitar "sim".
  `editai --desinstalar-voz` tira só o motor da voz sintetizada.
- **"O que você tem?" no passo 1.** Você marca o que tem (tema, roteiro, áudio, vídeo
  completo, vídeo da pessoa, personagem, cenas) e o Editai monta a trilha da edição.
- **20 bichos no avatar.** No lugar da cabeça de pessoa: cachorro, gato, raposa, panda,
  coelho, ovelha, pato, girafa, elefante, urso, leão, lobo, pinguim, porco, vaca, galinha,
  sapo, cavalo, lontra e guaxinim, com olhos e boca que falam. A **pelagem** pinta o bicho,
  o pescoço e as mãos.
- **O avatar de pessoa:**
  - a cabeça careca saiu lisa, um pouco menos redonda e mais perto da sobrancelha;
  - o boné e o gorro amassam o cabelo, em vez de cortá-lo reto;
  - os furos que mostravam a pele no cabelo chanel sumiram.

### Correções

- **No Safari, escolher um bicho às vezes não funcionava:** o clique se perdia enquanto a
  miniatura era desenhada.
- **O botão "Editar vídeo" pulava uns 230 px para baixo** quando o vídeo terminava de carregar.
  O espaço do vídeo agora já vem reservado.
- **O aviso de "Desinstalar a voz sintetizada"** mostra quanto o motor ocupa de verdade, e
  não mais "uns 3,5 GB".

## [0.1.0] — sem versão publicada

O Editai até 21/10/2026, instalado direto do código no GitHub:

- **A edição:** os cortes de silêncio, a legenda karaokê, os adesivos, o zoom de ênfase, os
  ícones automáticos, os efeitos sonoros e os presets.
- **A montagem em camadas:** o fundo, a biblioteca de cenas e, por cima, a pessoa, um
  personagem ou o seu avatar.
- **Com o Gemini, opcional:** a thumbnail, os cartões animados e a legenda em destaques.
- **A voz:** voz e bipe, efeitos na voz e a Minha voz (a sua voz narrando um roteiro).
- **O avatar em pixel art**, montado por partes.
