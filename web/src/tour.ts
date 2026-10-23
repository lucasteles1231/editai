/**
 * O tour guiado: começar pelo que se tem e, depois, cada parte da página, na ordem em que
 * aparece (dezesseis balões ao todo). Abre sozinho na primeira visita, e o botão "Tour" do
 * topo refaz.
 *
 * O balão abre ao lado do cartão (à direita na coluna das opções, à esquerda no painel):
 * por cima, ele cobria justamente as opções que estava explicando.
 */
import {type DriveStep, driver} from 'driver.js';
import 'driver.js/dist/driver.css';

const VISTO = 'editor-tour-visto';

const peca = (nome: string) => () => document.querySelector(`[data-tour="${nome}"]`) as Element;

export function comecarTour(): void {
  const passos: DriveStep[] = [
    {
      popover: {
        title: 'Comece pelo que você tem',
        description: 'Um vídeo seu falando, um roteiro, um áudio, uma pasta de cenas ou só o tema: você marca o '
          + 'que tem, e o editor monta o resto, com legenda, cortes, zoom, sons e thumbnail.<br><br>'
          + 'Tudo roda no seu computador: sem conta, sem assinatura e sem marca d\'água. Este tour passa por cada '
          + 'parte da página.',
      },
    },
    {
      element: '#antes-de-comecar',
      popover: {
        side: 'bottom',
        align: 'start',
        title: 'Antes de começar',
        description: 'Tudo aqui é opcional e se configura uma vez: <b>a sua voz</b>, gravada para narrar roteiros, '
          + '<b>o seu avatar</b> em pixel art, feito pela sua foto, e as '
          + 'chaves grátis do <b>Gemini</b> (ideias de capa, cartões e a matriz das cenas) e do <b>Pexels</b> (fotos '
          + 'para o fundo da capa). Cada cartão abre o próprio painel.',
      },
    },
    {
      element: peca('materiais'),
      popover: {
        side: 'right',
        align: 'start',
        title: '1. O que você tem?',
        description: 'Marque o que você tem: o <b>tema</b>, o <b>roteiro</b>, um <b>áudio</b>, o <b>vídeo '
          + 'completo</b> (o fundo, com ou sem alguém falando), o <b>vídeo da pessoa</b> para ir recortado por cima, '
          + 'um <b>personagem</b> ou uma pasta de <b>cenas</b>. Os arquivos são copiados para uma pasta do seu '
          + 'computador, não para a internet.',
      },
    },
    {
      element: peca('trilha'),
      popover: {
        side: 'right',
        align: 'start',
        title: 'A trilha',
        description: 'Com o que você marcou, o editor monta o caminho: de onde vem a <b>imagem</b>, quem vai '
          + '<b>por cima</b> (você, o seu avatar, um personagem ou ninguém) e de onde vem a <b>fala</b>, que dá a '
          + 'legenda e os cortes. Cada etapa pede só o que falta. Na montagem, <b>Ajustar as camadas</b> deixa trocar '
          + 'à mão quem vai por cima e de onde vem a fala.',
      },
    },
    {
      element: '#plataformas',
      popover: {
        side: 'right',
        align: 'start',
        title: 'Onde você vai postar',
        description: 'Marque uma ou várias: Shorts, TikTok, Reels, YouTube… O editor recomenda pelo formato do '
          + 'vídeo, a thumbnail sai no tamanho de cada uma e, na montagem, o vídeo sai em pé ou deitado.',
      },
    },
    {
      element: peca('presets'),
      popover: {
        side: 'right',
        align: 'start',
        title: '2. Os presets',
        description: 'Um ponto de partida para cada tipo de vídeo: vlog, gameplay, aula, review, podcast, notícia, '
          + 'imóveis e outros. Mexeu em algo, vira <b>Personalizado</b>, e <b>Salvar como preset</b> guarda o seu, '
          + 'que fica só neste computador e pode ser exportado.',
      },
    },
    {
      element: peca('interruptores'),
      popover: {
        side: 'right',
        align: 'start',
        title: 'As edições',
        description: 'Liga e desliga cada uma: cortar os silêncios, o zoom de ênfase, as palavras que saltam, os '
          + 'ícones automáticos, a pessoa mudando de lugar, a janela com câmera e os cartões animados, escritos pelo '
          + 'Gemini.',
      },
    },
    {
      element: peca('voz-e-bipe'),
      popover: {
        side: 'right',
        align: 'start',
        title: 'A voz e o bipe',
        description: 'A voz como foi gravada, <b>limpa</b> (sem eco, sem chiado e no mesmo volume) ou de '
          + '<b>estúdio</b>. No bipe, as palavras da lista ganham um bipe numa sílaba e asteriscos na legenda: '
          + '“porca**a”.',
      },
    },
    {
      element: peca('efeito-na-voz'),
      popover: {
        side: 'right',
        align: 'start',
        title: 'O efeito na voz',
        description: 'Robô, esquilo, cantado, rádio, fantasma e outros: 13 prontos, para qualquer voz. <b>Ouvir '
          + '8 s</b> toca a sua fala com o efeito. No <b>estúdio de voz</b>, você monta o seu de ouvido, compara com '
          + 'e sem efeito, e guarda.',
      },
    },
    {
      element: peca('ritmo'),
      popover: {
        side: 'right',
        align: 'start',
        title: 'O ritmo e o zoom',
        description: 'O <b>ritmo</b> decide quantos adesivos, ícones, zooms e sons entram, e o quanto perto um do '
          + 'outro. A pausa máxima diz o que vira corte, o respiro é o silêncio que fica no lugar, e os outros '
          + 'ajustam o zoom.',
      },
    },
    {
      element: peca('sons'),
      popover: {
        side: 'right',
        align: 'start',
        title: 'Os efeitos sonoros',
        description: 'Um som quando algo aparece, palavras que chamam o som delas (“dinheiro” toca moedas) e, se '
          + 'quiser, um clique em cada corte. Escolha o tema, ouça com <b>Ouvir</b> e ajuste o volume: os sons ficam '
          + 'sempre por baixo da voz.',
      },
    },
    {
      element: '#passo-legenda',
      popover: {
        side: 'right',
        align: 'start',
        title: '3. A legenda',
        description: 'O idioma e o tamanho do Whisper, que transcreve no seu computador. O estilo: <b>clássica</b>, '
          + 'em karaokê, ou <b>destaques</b>, com cores e uma pílula. Colando <b>o que você falou</b>, a legenda pega '
          + 'a grafia do texto. E a legenda à parte, em .srt e .vtt.',
      },
    },
    {
      element: '#passo-saida',
      popover: {
        side: 'right',
        align: 'start',
        title: '4. A saída',
        description: 'Formato (MP4, MOV, WebM, MKV ou GIF), codec, resolução, quadros por segundo e qualidade. Só '
          + 'aparece o que este computador consegue gravar.',
      },
    },
    {
      element: '#passo-thumb',
      popover: {
        side: 'right',
        align: 'start',
        title: '5. A thumbnail',
        description: 'Uma capa à parte, no tamanho de cada plataforma, em camadas: a pessoa recortada, o fundo '
          + '(outro quadro, desfocado, uma cor, uma foto do Pexels ou uma imagem gerada), a chamada, o ícone e a mão '
          + 'apontando. <b>Baixar</b> entrega como está.',
      },
    },
    {
      element: '#painel-ia',
      popover: {
        side: 'right',
        align: 'start',
        title: 'As ideias do Gemini',
        description: 'Com a chave, o Gemini lê o que você falou, olha 8 quadros do vídeo e sugere 3 capas, todas '
          + 'editáveis. O fundo gerado por IA é pago e só sai quando você clica.',
      },
    },
    {
      element: '#botao-editar',
      popover: {
        side: 'left',
        align: 'start',
        title: 'Editar e o resultado',
        description: '<b>Editar vídeo</b> começa, e a barra mostra cada etapa e quanto falta. Marque <b>só os '
          + 'primeiros 15 s</b> para testar o estilo rapidinho. No fim, assista e baixe o vídeo, as legendas e as '
          + 'thumbnails, ou abra a pasta onde tudo foi salvo.',
      },
    },
  ];
  const tour = driver({
    showProgress: true,
    progressText: '{{current}} de {{total}}',
    nextBtnText: 'Próximo',
    prevBtnText: 'Voltar',
    doneBtnText: 'Começar a editar',
    popoverClass: 'tour-editor',
    smoothScroll: true,
    allowClose: true,
    steps: passos,
    // O onDestroyStarted roda em qualquer fechamento (o Esc, o ×, o clique fora, o último
    // botão); o onDestroyed só roda se o balão atual já terminou de animar.
    onDestroyStarted: () => {
      try {
        localStorage.setItem(VISTO, '1');
      } catch {
        /* sem armazenamento: o tour só volta pelo botão */
      }
      tour.destroy();
    },
  });
  tour.drive();
}

export function tourJaVisto(): boolean {
  try {
    return localStorage.getItem(VISTO) === '1';
  } catch {
    return true;
  }
}
