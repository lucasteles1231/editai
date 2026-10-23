# Cartões animados

Com **Cartões animados** ligado no passo 2 e a chave do Gemini colada, ele lê a fala e
escreve os cartões, cada um preso à palavra em que o assunto é dito. Eles vieram de um
vídeo de notícia feito à mão no Remotion, e são desenhados aqui, quadro a quadro, com as
mesmas curvas e medidas:

| Cartão | O que faz | Som |
|---|---|---|
| **Selo** | uma etiqueta inclinada que entra com um pulo ("SEM CENSURA", "SEGUE PRA MAIS"); a do começo do vídeo cai carimbada | pop; o do começo, boom |
| **Lista** | de 2 a 4 itens que entram pela esquerda, cada um na sua palavra | whoosh e um clique por item |
| **Quadro** | um título e de 2 a 5 linhas (nome e valor) que entram uma a uma; a linha falada fica acesa | whoosh e um clique por linha |
| **Enquete** | dois botões, o certo e o errado, e depois o "COMENTA AÍ" | um clique por botão |
| **Carimbo** | um cartão que leva um carimbo vermelho ("APAGADA"), com tremida | whoosh e erro |
| **Destaque** | um número ou uma data grande que cai carimbado ("+18", "19 DE NOVEMBRO") | boom; na data, ding |
| **Flash** | o flash branco de uma foto e um selo ("FÃS PRINTARAM") | obturador |

- **O tempo:** tudo entra 100 ms antes da palavra, o que na tela lê como "no tempo".
- **Quantos:** um a cada 5 a 8 s de fala, sem sobrepor: o seguinte só entra depois do
  último item do anterior. O vídeo começa com um selo de gancho e, se a fala pede para
  seguir ou comentar, termina com outro.
- **Conferidos:** o editor confere cada cartão (o modelo, os campos, as palavras em
  ordem). O que vier errado volta para o Gemini uma vez, e o que continuar errado sai.
- **Sem o Gemini,** não há cartões: ficam os adesivos de palavra, e o resultado diz por
  quê.
- **Sem a janela** (no vídeo único ou na montagem de sempre), os cartões ficam no meio do
  quadro, longe da legenda.
- **Sem emoji colorido,** que o Pillow não desenha: no lugar dele vai um dos 122 ícones do
  editor, no traço de caneta.
- **No tema de sons Notícia** (o do preset), os sons são os do vídeo de referência: um
  whoosh na entrada, um clique em cada item depois do primeiro, o erro do Windows XP e o
  disco arranhado nos carimbos, um "vine boom" no número, um ding na data e o obturador no
  flash. O selo do gancho e o que explica um termo entram calados, e o que chama a
  audiência ("SEGUE PRA MAIS") leva um whoosh. Nenhum clique cai numa palavra com bipe.
