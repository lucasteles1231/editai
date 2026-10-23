# O que você falou

O Whisper não conhece o nome do seu projeto. Numa gravação de verdade, "Editai" saiu
"Edita I", "thumbnails" saiu "tambineios" e "presets" saiu "processos". No passo 3, o
campo **O que você falou** recebe o texto que você leu ou o roteiro que seguiu, e a
legenda pega a grafia dele:

- a palavra que bate com o texto fica escrita como no texto, com a pontuação dele;
- um trecho curto que o Whisper ouviu diferente pega a grafia do texto se as letras forem
  parecidas: "tambineios" e "thumbnails" são 50% parecidas. Uma palavra trocada de
  verdade ("plataforma" no lugar de "ferramenta", 30%) fica como foi dita;
- o que você improvisou fica como o Whisper ouviu, e o que você pulou não entra;
- as notas entre colchetes ("[pausa]"), o negrito do Markdown e os emojis saem.

Revise o texto antes: um erro de digitação dele vai para a legenda. Se o texto não for o
desta fala (menos da metade das palavras batem), a legenda fica com o Whisper. O texto
não entra nos presets, porque é de um vídeo só. No terminal: `--texto-falado texto.txt`.
