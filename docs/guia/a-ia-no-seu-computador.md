# A IA no seu computador

Opcional. Sem a chave do Gemini, a IA local escreve o roteiro e os cartões, escolhe as cenas,
descreve a biblioteca, monta o avatar pela foto e sugere as capas. Ela roda no seu
computador, sem internet e sem chave, e nada do que você manda sai dele.

O modelo é o [Qwen3.5-4B](https://huggingface.co/Qwen/Qwen3.5-4B), de código aberto (Apache
2.0). O programa que o roda é o `llama-server`, do [llama.cpp](https://github.com/ggml-org/llama.cpp)
(MIT).

1. **Instale.** Em **Antes de começar**, no cartão **A IA**, clique em **Instalar a IA
   local**. São uns 3,5 GB, baixados uma vez, que levam de 3 a 10 minutos conforme a
   internet. O programa e o modelo são conferidos pelo SHA-256 antes de valer. No terminal:
   `editai --instalar-ia`.
2. **Escolha quem responde.** No mesmo cartão:
   - **Automática** (o padrão): o Gemini, se houver a chave, e, sem ela, a local;
   - **Gemini**;
   - **IA local**.

   No terminal, `--ia automatica|gemini|local` vale para uma edição.
3. **Use como sempre.** Ela entra onde o Gemini entraria. Se a escolhida falhar, o editor
   avisa e para: ele não troca de IA sozinho.

**Para desinstalar,** use o link do mesmo cartão, ou `editai --desinstalar-ia`. A pasta
inteira sai.

## O que ela faz bem, e o que não

Ela foi medida contra o Gemini nas tarefas do editor, com as mesmas entradas, num MacBook M5
(26/10/2026):

| Tarefa | A IA local | O Gemini |
|---|---|---|
| a matriz: descrever 19 fotos de um imóvel | 18 certas | 19 certas |
| o avatar pela foto | acerta o cabelo, a barba e os óculos; errou a cor dos olhos | acerta |
| os cartões de um vídeo falado | de 3 a 9 | de 4 a 14 |
| o corte para 45 s | 47 e 51 s | 46 e 44 s |
| o roteiro pelo tema (45 s, umas 117 palavras) | 184 e 198 palavras, mesmo depois do conserto | 127 e 118 |
| os fatos do roteiro | erra mais: disse que "com o Sol mais longe o céu seria preto" | explicou certo |

**Na prática:**
- **ela é boa nas tarefas de estrutura:** as cenas, os cortes, a matriz, as buscas das
  fotos e o avatar;
- **no roteiro escrito do zero, revise com mais cuidado:** ele sai mais longo, e um fato
  pode vir errado.

## O que precisa

Medido num MacBook M5 com 16 GB:

| | Com a placa de vídeo | Só no processador |
|---|---|---|
| a velocidade, escrevendo | 31 palavras-pedaço (tokens) por segundo | 16 |
| as cenas e os cartões de um vídeo de 34 s | 82 s | 332 s |
| o roteiro pelo tema | de 7 a 21 s | de 17 a 50 s |
| a memória | 5,5 GB | 8,1 GB |
| o disco | uns 3,5 GB | o mesmo |

- **A placa:** no Mac com chip Apple, ela usa a placa sempre. No Windows e no Linux, o
  editor instala o pacote com Vulkan (qualquer placa: NVIDIA, AMD ou Intel) e, se ele não
  abrir, o de processador.
- **Num notebook comum, só no processador,** conte com bem mais tempo que o do M5: o
  roteiro de um vídeo de 2 min pode passar de 15 minutos.
- **Com 8 GB de memória,** feche os outros programas antes de editar.

O servidor da IA sobe no primeiro pedido (1 s, depois de instalado) e fecha sozinho 5
minutos depois do último, para devolver a memória.

## Por que este modelo

Quatro modelos abertos foram medidos nas mesmas tarefas:

| Modelo | O que pesou |
|---|---|
| **Qwen3.5-4B** (o escolhido) | descreveu certo 18 de 19 fotos e ocupa 5,5 GB |
| Gemma 4 E4B | escreve um pouco melhor e faz mais cartões, mas acertou 12 de 19 fotos e ocupa 7,2 GB |
| Gemma 4 E2B | o mais rápido (2 vezes os outros) e o mais leve (4,6 GB), mas acertou 6 de 19 fotos |
| Qwen3-VL-4B | não fez nenhum cartão, ocupa 8,2 GB e errou a física do céu azul |
