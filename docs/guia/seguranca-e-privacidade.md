# Segurança e privacidade

O editor roda no seu computador, e quase nada sai dele. Esta seção diz o que sai, o que
protege a página, como o que é baixado é conferido e o que a última verificação achou
(10/10/2026).

**O que sai do computador:**

| O quê | Para onde | Quando |
|---|---|---|
| nada do vídeo, do áudio nem da sua voz | — | nunca: a transcrição, o recorte, a edição e a Minha voz rodam no computador |
| o texto da fala e 8 quadros pequenos (512 px) | Google (Gemini) | só com a sua chave, nas ideias de thumbnail |
| o texto da fala | Google (Gemini) | só com a sua chave e o roteiro ligado (cenas, cartões e destaques) |
| 3 quadros pequenos de cada clipe | Google (Gemini) | só quando você clica em **Gerar a matriz** |
| a descrição de uma cena | Google (Gemini) | só quando você gera um fundo (pago) |
| a foto do avatar, reduzida a 1024 px e sem os metadados (o lugar e o aparelho) | Google (Gemini) | só quando você clica em **Montar pela foto com o Gemini**; o Editai não guarda a foto |
| o texto da busca | Pexels | só com a chave do Pexels, quando você busca uma foto |
| os pedidos de download | GitHub, `astral.sh` (o uv), PyPI, Hugging Face e `remotion.media` | na instalação e no primeiro uso de cada modelo ou som |
| o pedido da última versão publicada, sem nada seu | GitHub (`api.github.com`) | uma vez por dia, ao abrir o editor; desliga com "Não avisar mais", na faixa do aviso, ou com `EDITAI_SEM_AVISO_DE_VERSAO=1` ([Atualizar](./instalacao-em-detalhe#atualizar)) |

**O que protege a página:**

- **Só o seu computador alcança.** O servidor escuta em `127.0.0.1`: outro aparelho da
  rede não chega nele.
- **Só quem abriu.** Cada sessão tem um token aleatório, que vai em todo pedido à API e é
  comparado em tempo constante. A página tira o token da barra de endereço assim que abre.
- **Nenhum site de fora manda no editor.** O `Host` e o `Origin` de cada pedido são
  conferidos, então um site aberto no mesmo navegador não consegue mandar o editor
  trabalhar, nem com o truque de apontar um domínio para `127.0.0.1`.
- **A página só roda o código do próprio editor.** A política de conteúdo (CSP) barra
  script de fora e script na linha, e a página não pode ser posta dentro de outra. O
  endereço, com o token, nunca vai no `Referer`. Os testes da página, nos três
  navegadores, falham se a política barrar qualquer coisa.
- **Os arquivos que chegam** perdem o caminho e os caracteres estranhos no nome. As
  fontes e as mãos saem de uma lista fixa, as vozes e os avatares, de um nome validado, os
  36 quadros do avatar precisam ser PNG de 900 × 900, e há tetos para a matriz (2 MB), o
  roteiro (20.000 letras) e a foto do avatar (20 MB).

**As chaves** (Gemini e Pexels) ficam no `config.json`, que só o seu usuário consegue ler
(permissão 0600). Elas vão no cabeçalho do pedido, nunca no endereço, e nunca voltam para
a página, que só mostra os quatro últimos caracteres.

**O que é baixado, e como é conferido:**

| O quê | De onde | A conferência |
|---|---|---|
| os modelos do Whisper | Hugging Face (Systran) | um commit fixo, o que foi testado |
| o modelo do recorte (MODNet) | Hugging Face (Xenova) | um commit fixo |
| os 4 sons do tema Notícia sem licença livre | `remotion.media` | o SHA-256 de cada arquivo: o diferente é descartado, e toca a reserva da Kenney |
| o modelo da Minha voz | Hugging Face (Qwen) | um commit fixo |
| as bibliotecas da Minha voz | PyPI | as versões testadas, em [`editor/recursos/motor-de-voz-versoes.txt`](https://github.com/lucasteles1231/editai/blob/main/editor/recursos/motor-de-voz-versoes.txt) |
| as bibliotecas do editor | PyPI, pelo uv | as versões mínimas do `pyproject.toml`; o CI testa as do `uv.lock` |

**A verificação de 10/10/2026:**

- **O código:** as rotas do servidor, os envios, os downloads e os subprocessos foram
  lidos. Nenhum comando passa por um shell, e nenhum arquivo é aberto com `pickle` ou
  `torch.load`. O histórico do git não tem nenhuma chave.
- **As dependências:** nenhuma vulnerabilidade conhecida. O
  [`pip-audit`](https://github.com/pypa/pip-audit) conferiu as 37 bibliotecas do editor e
  as 20 de desenvolvimento, e o `npm audit`, as da página.
- **A Minha voz:** o `qwen-tts` 0.1.1 exige o `transformers` 4.57.3 e o `accelerate`
  1.12.0, que têm 7 avisos conhecidos (como o CVE-2026-4372). Todos dependem de carregar
  um modelo malicioso. O motor carrega só o modelo oficial da Qwen, no commit fixo, sem
  `trust_remote_code`, e os `config.json` dele não têm os campos usados nesses ataques.
  Quando sair um `qwen-tts` com as versões corrigidas, o editor atualiza. Ele também traz
  o Gradio, uma interface web que o motor nunca abre.
- **O CI:** os workflows só têm permissão de leitura no repositório.

**Os limites:**

- **Quem usa a sua conta do computador**, ou um programa rodando nela, lê os vídeos, as
  vozes e o `config.json`. O editor não criptografa nada: eles são arquivos seus como
  qualquer outro.
- **A página é `http`, sem o cadeado.** Isso é normal num endereço local: nada passa pela
  rede.
- **A autorização da Minha voz** é conferida pelo Whisper. Ela evita usar uma gravação
  qualquer por engano, mas não impede quem altera o código, que é aberto. Clonar a voz
  de outra pessoa sem a permissão dela é ilegal.
- **O que o Gemini escreve** é conferido no formato e nos tempos, mas o conteúdo das
  cenas, dos cartões e das ideias é dele. Revise antes de postar.

**Achou uma falha?** Não abra uma issue pública: use o
[aviso privado](https://github.com/lucasteles1231/editai/security/advisories/new)
(**Report a vulnerability**, na aba Security). Veja o [SECURITY.md](https://github.com/lucasteles1231/editai/blob/main/SECURITY.md).
