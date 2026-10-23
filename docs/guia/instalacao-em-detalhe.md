# Instalação em detalhe

## O que o instalador faz

O instalador de cada sistema ([Baixar](../baixar)) faz três coisas, e só elas:

1. **Instala o [uv](https://docs.astral.sh/uv/), se faltar.** O uv cuida do Python para o
   Editai sem mexer no do sistema. Se você já tem o uv, ele usa o seu.
2. **Instala o Editai na versão do instalador,** num ambiente só dele, criado pelo uv. O
   pacote vem da [página da versão](https://github.com/lucasteles1231/editai/releases) no
   GitHub.
3. **Cria o atalho "Editai"** (`editai --criar-atalho`):
   - **macOS:** o app Editai, em Aplicativos (e no Launchpad);
   - **Windows:** o atalho no menu Iniciar e na Área de Trabalho;
   - **Linux:** o item no menu de aplicativos.

O atalho abre o Editai numa janela do terminal, e o navegador abre sozinho no editor. A
janela do terminal é o Editai rodando: fechar ela fecha o editor, como o `Ctrl+C`.

Os instaladores são scripts curtos, e dá para ler antes de rodar:
[`instalar.sh`](https://github.com/lucasteles1231/editai/blob/main/instalador/instalar.sh)
(macOS e Linux) e
[`instalar.ps1`](https://github.com/lucasteles1231/editai/blob/main/instalador/instalar.ps1)
(Windows). Cada versão publica, junto, os hashes SHA-256 de todos os arquivos
(`SHA256SUMS.txt`).

**Por que o aviso de segurança no arquivo baixado.** Um instalador sem assinatura paga
(a conta de desenvolvedor da Apple ou um certificado no Windows) é avisado pelo sistema na
primeira vez. O comando de uma linha não passa por esse aviso, porque ele não baixa um
arquivo marcado como "vindo da internet".

## O que é instalado, e onde

| O quê | Tamanho | Onde fica |
|---|---|---|
| O uv | ~45 MB | Windows: `%USERPROFILE%\.local\bin` · macOS e Linux: `~/.local/bin` |
| O Python 3.12, se você ainda não tiver | ~75 MB | dentro da pasta do uv |
| O editor e o que ele usa | ~220 MB | um ambiente só dele, criado pelo uv |
| O atalho Editai | ~150 KB | macOS: `~/Applications/Editai.app` · Windows: o menu Iniciar e a Área de Trabalho · Linux: `~/.local/share/applications/editai.desktop` |
| O modelo do Whisper (`small`) | 464 MB | Windows: `%USERPROFILE%\.cache\huggingface` · macOS e Linux: `~/.cache/huggingface` |
| O modelo do recorte (MODNet), na primeira vez que a pessoa é recortada | 26 MB | a mesma pasta do Hugging Face |
| A voz sintetizada (Minha voz), só se você instalar: o ambiente e o modelo | ~3,5 GB | `motor-de-voz`, na pasta de dados: `%LOCALAPPDATA%\editor-de-video` (Windows), `~/Library/Application Support/editor-de-video` (macOS) ou `~/.local/share/editor-de-video` (Linux) |
| As vozes gravadas: a leitura e a referência de cada uma | ~15 MB cada | `vozes`, na mesma pasta de dados |
| Os avatares | ~1 MB cada | `avatares`, na mesma pasta de dados |
| Os seus presets | poucos KB | `presets.json`, na mesma pasta de dados |
| Os seus efeitos na voz | poucos KB | `efeitos-de-voz.json`, na mesma pasta de dados |
| As chaves do Gemini e do Pexels, se você colar | — | `config.json`, na pasta de configuração: a mesma de dados no Windows e no macOS, `~/.config/editor-de-video` no Linux |
| A última versão vista no GitHub (o aviso de versão nova) | 1 KB | `versao.json`, na mesma pasta de configuração |
| Os vídeos editados e as thumbnails | — | `editor-de-video`, dentro da pasta **Vídeos** (Windows e Linux) ou **Filmes** (macOS) |

As pastas ainda se chamam `editor-de-video`, o nome de antes do Editai: assim, quem já
usava não perde a chave, as vozes nem os presets.

O vídeo que você envia pela página é copiado para a pasta de cache do sistema
(`%LOCALAPPDATA%\editor-de-video\Cache` no Windows, `~/Library/Caches/editor-de-video`
no macOS e `~/.cache/editor-de-video` no Linux), e as cópias com mais de 2 dias são
apagadas sozinhas.

Não é preciso instalar FFmpeg, Node nem nada mais: o FFmpeg vem dentro do pacote de
vídeo do Python ([PyAV](https://github.com/PyAV-Org/PyAV)).

## Os modelos de transcrição

| Modelo | Download | Quando usar |
|---|---|---|
| `tiny` | 75 MB | computador bem modesto; erra mais |
| `base` | 145 MB | mais rápido que o padrão, para testes |
| **`small`** | **464 MB** | **o padrão:** o menor que transcreve português sem tropeçar a cada frase |
| `medium` | 1,5 GB | sotaque forte, áudio ruim ou termos técnicos; bem mais lento |

Escolha na página (passo 3) ou com `--modelo`. Cada modelo é baixado na primeira vez que
for usado.

## As versões

Cada versão do Editai tem um número, como `0.2.0`, e uma
[página no GitHub](https://github.com/lucasteles1231/editai/releases), com o pacote, os
instaladores e o que mudou. A lista completa está em [Versões](../versoes).

- **O número** segue o [versionamento semântico](https://semver.org/lang/pt-BR/): o último
  muda nas correções, o do meio nas novidades e o primeiro quando algo deixa de funcionar
  como antes.
- **A sua versão:** `editai --versao`, ou o rodapé da página do editor.

## Atualizar

**O aviso de versão nova.** Uma vez por dia, o Editai pergunta ao GitHub qual é a última
versão publicada. Se for mais nova que a sua, a página mostra uma faixa amarela com o que
mudou e o comando para atualizar.

- **O que sai do computador:** só o pedido da última versão ao GitHub
  (`api.github.com`), sem nada seu. Veja [Segurança e privacidade](./seguranca-e-privacidade).
- **Sem internet,** o Editai abre igual, só sem o aviso.
- **Para desligar:** "Não avisar mais", na própria faixa, ou a variável de ambiente
  `EDITAI_SEM_AVISO_DE_VERSAO=1`.

**Para atualizar:**

- **macOS e Linux:** feche o Editai e rode `editai --atualizar`. Ele instala a última versão
  por cima, e as suas vozes, avatares, presets e chaves continuam onde estavam.
- **Windows:** feche o Editai e rode o instalador de novo (o comando de [Baixar](../baixar)).
  O `editai.exe` aberto não deixa trocar o programa, por isso o `--atualizar` só mostra o
  comando.

Rodar o instalador de novo também atualiza, em qualquer sistema.

## Desinstalar

Para desinstalar tudo (o motor da voz, as vozes gravadas, os avatares, os presets, as
chaves, os temporários, o atalho e o programa):

```bash
editai --desinstalar
```

Ele mostra o que vai sair, com o tamanho de cada coisa, e só apaga depois de você digitar
**sim**.

- **Perguntados à parte:** os modelos de transcrição e de recorte (na pasta do Hugging
  Face, que outros programas também usam) e os vídeos editados. No Enter, eles ficam.
- **Sem perguntas:** `--sim` não pergunta nada. Aí os modelos e os vídeos só saem com
  `--com-modelos` e `--com-videos`.
- **No Windows,** o último passo é seu: feche o Editai e rode `uv tool uninstall editai`.
- **As chaves do Gemini e do Pexels** saem do computador, mas continuam valendo nos
  serviços. Para cancelar a do Gemini, apague-a em
  [aistudio.google.com/apikey](https://aistudio.google.com/apikey).
- **O uv fica:** ele é uma ferramenta geral, e não do Editai. Para tirar também, veja a
  [documentação do uv](https://docs.astral.sh/uv/getting-started/installation/#uninstallation).

Para tirar só a voz sintetizada, use o link **Desinstalar a voz sintetizada**, na página,
ou `editai --desinstalar-voz`. As vozes gravadas ficam, para quando você instalar de novo.

## Instalar sem o instalador

Os mesmos passos, à mão, num terminal (o PowerShell no Windows):

1. Instale o uv, se ainda não tiver:

   ```bash
   # macOS e Linux
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

   ```powershell
   # Windows
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

2. **Feche o terminal e abra de novo**, e instale o Editai. A última versão publicada:

   ```bash
   uv tool install https://github.com/lucasteles1231/editai/releases/download/vX.Y.Z/editai-X.Y.Z-py3-none-any.whl
   ```

   (troque `X.Y.Z` pelo número da [última versão](../versoes)). Ou a versão em
   desenvolvimento, direto do código, com o que ainda não saiu numa versão:

   ```bash
   uv tool install --force https://github.com/lucasteles1231/editai/archive/refs/heads/main.zip
   ```

3. Se quiser o atalho: `editai --criar-atalho`. Para abrir: `editai`.

Se você instalou quando o projeto ainda se chamava **editor-de-video**, troque uma vez,
desinstalando o antigo antes (os seus vídeos, presets, vozes e a chave continuam onde
estavam):

```bash
uv tool uninstall editor-de-video
```

e instale de novo, pelo instalador ou pelos passos acima.
