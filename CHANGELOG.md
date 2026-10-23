# Versões

O que mudou em cada versão do Editai. Cada versão publicada tem os instaladores e o pacote
na [página dela no GitHub](https://github.com/lucasteles1231/editai/releases), e a mais nova
está sempre no [site](https://lucasteles1231.github.io/editai/baixar).

Os números seguem o [versionamento semântico](https://semver.org/lang/pt-BR/): o último muda
nas correções, o do meio nas novidades e o primeiro quando algo deixa de funcionar como antes.

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
