# Dúvidas e problemas

<details>
<summary><b><code>editai</code> não é reconhecido como comando</b></summary>

O instalador do uv põe a pasta dos comandos (`.local/bin`) no PATH, mas só as janelas
abertas **depois** dele enxergam. Feche o terminal e abra de novo. No macOS, dá para
resolver na mesma janela:

```bash
source ~/.local/bin/env
```

Se ainda assim não funcionar, rode `uv tool update-shell`, feche e abra de novo.

</details>

<details>
<summary><b>O instalador do uv avisou "shadowed by other commands"</b></summary>

Você já tinha outro `uv` no computador, instalado pelo `pip` ou pelo Homebrew por
exemplo, e ele vem antes no PATH. Isso não atrapalha: qualquer um dos dois instala o
editor, e o comando `editai` vai para a mesma pasta.

Se quiser ficar com um só, desinstale o antigo pelo mesmo caminho por onde ele veio:
`pip uninstall uv` ou `brew uninstall uv`.

</details>

<details>
<summary><b>Windows 11: "Uma política de Controle de Aplicativo bloqueou este arquivo"</b></summary>

O erro completo é parecido com este:

```
ImportError: DLL load failed while importing logging: Uma política de Controle de
Aplicativo bloqueou este arquivo.
```

(Em inglês: *An Application Control policy has blocked this file*.)

- **Quem bloqueia:** o Controle Inteligente de Aplicativos (Smart App Control) do
  Windows 11. Ele barra arquivos sem assinatura que a Microsoft ainda não conhece, como
  os do PyAV, a biblioteca que lê e grava o vídeo. Com ele ligado, o editor não abre.
- **O que não resolve:** instalar o Visual C++ ou liberar o editor no antivírus. É outra
  camada do Windows.
- **Como resolver:** desligue o Controle Inteligente de Aplicativos em **Segurança do
  Windows → Controle de aplicativos e do navegador → Configurações do Controle
  Inteligente de Aplicativos → Desligado**.
- **Dá para ligar de novo?** Num Windows 11 atualizado (da atualização de abril de 2026
  em diante), sim. Antes dela, desligar só volta reinstalando o Windows. Por isso, rode
  o Windows Update antes.
- **Computador de empresa:** o bloqueio pode vir de uma regra da TI. Nesse caso, fale com
  ela.

O próprio editor reconhece esse erro e mostra estes passos no lugar do traceback.

</details>

<details>
<summary><b>Windows: erro de DLL ao transcrever ou ao recortar a pessoa</b></summary>

O modelo de transcrição e o do recorte precisam do "Microsoft Visual C++
Redistributable", que a maioria dos computadores já tem. Se aparecer um erro com
`DLL load failed` que **não** fala em política de Controle de Aplicativo (esse está no
item acima), instale a versão x64
[direto da Microsoft](https://aka.ms/vs/17/release/vc_redist.x64.exe) e tente de novo.

</details>

<details>
<summary><b>A thumbnail com IA avisou que a cota acabou</b></summary>

A cota gratuita do Gemini conta pedidos por modelo e por dia. O editor tenta três
modelos antes de desistir, e o aviso diz quando a cota volta. Se você usa muito, ative o
faturamento no [Google AI Studio](https://aistudio.google.com/): a cota sobe, e o Google
cobra pelo uso, conforme a [tabela de preços](https://ai.google.dev/gemini-api/docs/pricing).

</details>

<details>
<summary><b>Onde a chave fica guardada, e como apagar</b></summary>

No `config.json` da pasta de configuração do editor (veja "O que é instalado, e onde"),
que só o seu usuário consegue ler. A página só mostra os quatro últimos caracteres. Para
apagar, use o botão **Remover chave** no painel do cartão da chave, em **Antes de
começar**, ou apague o arquivo.

</details>

<details>
<summary><b>O antivírus ou o firewall reclamou</b></summary>

O editor abre um pequeno servidor que só aceita conexões do seu próprio computador
(`127.0.0.1`), por isso o firewall não deve perguntar nada. Se o antivírus bloquear o
`editai`, autorize: ele foi instalado pelo uv, a partir deste repositório.

</details>

<details>
<summary><b>"Address already in use" ou porta ocupada</b></summary>

O editor escolhe uma porta livre sozinho. Se você fixou uma com `--porta`, escolha outra,
por exemplo `editai --porta 8765`.

</details>

<details>
<summary><b>A legenda saiu errada ou em outro idioma</b></summary>

- Confira o **idioma da fala** no passo 3 (ou `--idioma`).
- Com áudio ruim, sotaque forte ou muitos termos técnicos, use o modelo `medium`.
- Um microfone perto da boca ajuda mais que qualquer modelo.

</details>

<details>
<summary><b>O vídeo ficou deitado</b></summary>

O editor endireita o vídeo pela informação de rotação que o celular grava no arquivo. Se
o arquivo veio de um app que apagou essa informação, gire o vídeo antes de editar.

</details>

<details>
<summary><b>A primeira edição demorou muito</b></summary>

Na primeira vez, o editor baixa o modelo de transcrição (464 MB no `small`). Das próximas
vezes, ele já está no computador.

</details>

<details>
<summary><b>A Minha voz não ficou parecida, ou leu uma palavra errado</b></summary>

- **Parecida:** grave de novo num lugar mais silencioso, perto do microfone, no seu jeito
  normal de falar (como num vídeo, e não como quem lê). A voz copia o volume, o cômodo e
  o ritmo da gravação.
- **Uma palavra:** siglas e nomes estrangeiros vão na lista de **Pronúncia**
  (`PEGI = pégui`). A legenda continua com a grafia do roteiro.
- **A instalação falhou:** a página mostra as últimas linhas do erro. Confira a internet e
  o espaço livre (uns 3,5 GB) e clique em **Instalar** de novo.

</details>

<details>
<summary><b>Dá para usar sem internet?</b></summary>

Sim, depois que os modelos foram baixados uma vez, e a Minha voz também, depois de
instalada. Só as partes opcionais da thumbnail precisam de internet: as ideias do Gemini,
as fotos do Pexels e o fundo gerado. Mesmo
nelas, a página só fala com o seu computador, e é o editor que busca o resto.

</details>
