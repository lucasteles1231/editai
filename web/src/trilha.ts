/**
 * A trilha do passo 1: a pessoa marca o que tem (o tema, o roteiro, o áudio, o vídeo
 * completo…), e daqui sai o caminho do vídeo, já como o modo e as camadas que o resto da
 * página entende. É o que o dono pediu em 20/10/2026: começar pelo que se tem, e não pelo
 * jeito de montar.
 *
 * - **A imagem:** o vídeo completo; senão, as cenas. Com os dois, as cenas são o fundo e o
 *   vídeo completo (a pessoa falando nele) vai por cima, recortado. Só o vídeo da pessoa, sem
 *   fundo nenhum, é o vídeo inteiro.
 * - **Por cima:** o vídeo da pessoa, o personagem ou, quando ninguém fala na tela (a fala é
 *   um áudio ou uma narração), o avatar salvo. A pessoa pode trocar por "ninguém".
 * - **A fala** (de onde saem a legenda e os cortes): o áudio; senão, o som do vídeo de quem
 *   fala; senão, o roteiro narrado. "Narrar o roteiro" troca o som do vídeo pela narração.
 * - **O texto:** o roteiro corrige a grafia da legenda (e é o que a voz lê); o tema vai de
 *   contexto para o Gemini.
 *
 * Só um vídeo, falando, sem mais nada, continua sendo o modo ``'um'``: o caminho simples.
 */
import type {Fala, FonteDoFundo, Modo, PorCima} from './tipos';

export type Material = 'tema' | 'roteiro' | 'audio' | 'completo' | 'pessoa' | 'personagem' | 'cenas';

/** As pílulas, na ordem em que aparecem, com o que cada uma quer dizer. */
export const MATERIAIS: [Material, string, string][] = [
  ['tema', 'Tema', 'o assunto do vídeo, em uma frase'],
  ['roteiro', 'Roteiro', 'o texto do vídeo'],
  ['audio', 'Áudio', 'a fala gravada, sem imagem'],
  ['completo', 'Vídeo completo', 'o vídeo de fundo, com ou sem alguém falando nele'],
  ['pessoa', 'Vídeo da pessoa', 'você falando, para ir por cima do fundo, recortado'],
  ['personagem', 'Personagem', 'um GIF que fala por você'],
  ['cenas', 'Cenas', 'uma pasta de vídeos e fotos, escolhidos pelo que é dito'],
];

/** O que a página já sabe dos arquivos e das escolhas. */
export type Fatos = {
  /** O som de cada vídeo; ``null`` enquanto ele não sobe (conta como se tivesse). */
  completoTemSom: boolean | null;
  pessoaTemSom: boolean | null;
  temAvatar: boolean;
  /** "Narrar o roteiro" no lugar do som do vídeo. */
  narrar: boolean;
  /** Quem vai por cima quando nenhum vídeo nem personagem veio: a escolha (``null``, a regra). */
  porCima: 'avatar' | 'nada' | null;
};

/** Onde um vídeo enviado entra: como o vídeo único, como o fundo ou por cima. */
export type Destino = 'unico' | 'fundo' | 'pessoa' | null;

export type Etapa = {id: 'texto' | 'imagem' | 'por-cima' | 'fala'; titulo: string; texto: string};

export type Trilha = {
  modo: Modo;
  fonteDoFundo: FonteDoFundo;
  porCima: PorCima;
  /** De onde vem a fala na montagem; ``null`` no vídeo único (é o som dele). */
  fala: Fala | null;
  completo: Destino;
  daPessoa: Destino;
  /** Por cima, quando não vem de um vídeo nem do personagem, a pessoa escolhe. */
  escolhePorCima: boolean;
  /** Dá para trocar o som do vídeo pela narração do roteiro. */
  podeNarrar: boolean;
  etapas: Etapa[];
  /** Por que ainda não dá para editar ("" quando dá). */
  bloqueio: string;
};

/** O que só chega numa próxima versão (as fases 2 e 3 do plano de 20/10/2026). */
export const AINDA_NAO = {
  tema: 'Só com o tema, o Gemini vai escrever o roteiro: isso chega numa próxima versão. Por enquanto, marque '
    + 'Roteiro e escreva o texto.',
  imagem: 'Sem vídeo e sem cenas, o Editai vai achar fotos pelo que é dito: isso chega numa próxima versão. Por '
    + 'enquanto, marque o vídeo completo ou as cenas.',
};

export function montarTrilha(tem: ReadonlySet<Material>, f: Fatos): Trilha {
  const t: Trilha = {
    modo: 'montagem', fonteDoFundo: 'video', porCima: 'nada', fala: null, completo: null, daPessoa: null,
    escolhePorCima: false, podeNarrar: false, etapas: [], bloqueio: '',
  };
  if (!tem.size) return {...t, modo: 'um', bloqueio: 'Marque o que você tem.'};
  const bloquear = (motivo: string) => {
    t.bloqueio ||= motivo;
  };
  const cenas = tem.has('cenas');
  const completo = tem.has('completo');
  const pessoa = tem.has('pessoa');
  const personagem = tem.has('personagem');
  const roteiro = tem.has('roteiro');

  // A imagem, e quem fala na tela.
  let imagem: string;
  let falante: 'completo' | 'pessoa' | null = null;     // o vídeo de quem fala, se houver
  let porCimaDeVideo: 'completo' | 'pessoa' | null = null;
  if (cenas) {
    t.fonteDoFundo = 'cenas';
    imagem = 'As cenas da sua pasta, escolhidas pelo que é dito: pelo Gemini ou, sem ele, pelas palavras.';
    if (completo && pessoa) {
      bloquear('Com as cenas, o vídeo completo vai por cima, no lugar do vídeo da pessoa: desmarque um dos dois.');
    }
    porCimaDeVideo = completo ? 'completo' : pessoa ? 'pessoa' : null;
  } else if (completo) {
    imagem = 'O vídeo completo, inteiro, de fundo.';
    porCimaDeVideo = pessoa ? 'pessoa' : null;
    falante = 'completo';
  } else if (pessoa) {
    imagem = 'O vídeo da pessoa é o vídeo inteiro.';
    falante = 'pessoa';
  } else {
    imagem = 'Fotos achadas pelo que é dito (numa próxima versão).';
    bloquear(AINDA_NAO.imagem);
  }
  if (porCimaDeVideo) falante = porCimaDeVideo;
  if (personagem && porCimaDeVideo) bloquear('Por cima vai a pessoa ou o personagem, um só: desmarque um dos dois.');
  const somDe = (v: 'completo' | 'pessoa') => (v === 'completo' ? f.completoTemSom : f.pessoaTemSom) !== false;

  // A fala: o áudio; o som de quem fala; o roteiro narrado.
  let fala: string;
  const doVideo = falante !== null && somDe(falante);
  t.podeNarrar = roteiro && doVideo && !tem.has('audio');
  if (tem.has('audio')) {
    t.fala = 'audio';
    fala = 'O áudio que você enviar: dele saem a legenda e os cortes.';
  } else if (doVideo && !(t.podeNarrar && f.narrar)) {
    t.fala = porCimaDeVideo ? 'pessoa' : 'fundo';
    fala = `O som do ${falante === 'completo' ? 'vídeo completo' : 'vídeo da pessoa'}: dele saem a legenda e os cortes.`;
  } else if (roteiro) {
    t.fala = 'voz';
    fala = 'A sua voz narra o roteiro: da narração saem a legenda e os cortes.';
  } else if (tem.has('tema')) {
    fala = 'O roteiro escrito pelo tema, narrado (numa próxima versão).';
    bloquear(AINDA_NAO.tema);
  } else if (falante !== null) {
    t.fala = porCimaDeVideo ? 'pessoa' : 'fundo';
    fala = 'O vídeo não tem som: ele sai sem cortes e sem legenda.';
  } else if (cenas) {
    t.fala = 'cenas';
    fala = 'O som dos vídeos da pasta que você marcar, na ordem dos números: dele saem a legenda e os cortes. '
      + 'Sem som nas cenas, marque o áudio ou o roteiro.';
  } else {
    fala = 'Falta a fala.';
  }

  // Por cima.
  let porCima: string;
  if (porCimaDeVideo) {
    t.porCima = 'pessoa';
    porCima = porCimaDeVideo === 'completo'
      ? 'O vídeo completo, com a pessoa recortada por cima das cenas.' : 'Você, recortado do vídeo da pessoa.';
  } else if (personagem) {
    t.porCima = 'personagem';
    porCima = 'O personagem, mexendo a boca quando a voz fala.';
  } else {
    t.escolhePorCima = true;
    const narrada = t.fala === 'audio' || t.fala === 'voz';
    t.porCima = f.porCima ?? (narrada && f.temAvatar ? 'avatar' : 'nada');
    porCima = t.porCima === 'avatar' ? 'O seu avatar, mudando de pose a cada frase.'
      : 'Ninguém: só a imagem, com a legenda e as animações.';
  }

  // O modo: um vídeo só, falando, sem nada por cima, é o vídeo único.
  const principal = completo && !cenas ? 'completo' : pessoa && !completo && !cenas ? 'pessoa' : null;
  const sozinho = principal !== null && t.porCima === 'nada' && (t.fala === 'fundo' || t.fala === null);
  if (sozinho) {
    t.modo = 'um';
    t.fala = null;
    imagem = principal === 'completo' ? 'O vídeo completo: é ele que sai editado.'
      : 'O vídeo da pessoa: é ele que sai editado.';
    if (principal === 'completo') t.completo = 'unico';
    else t.daPessoa = 'unico';
  } else {
    if (principal === 'completo') t.completo = 'fundo';
    else if (principal === 'pessoa') t.daPessoa = 'fundo';
    if (porCimaDeVideo === 'completo') t.completo = 'pessoa';
    else if (porCimaDeVideo === 'pessoa') t.daPessoa = 'pessoa';
  }

  const textos: string[] = [];
  if (roteiro) {
    textos.push(t.fala === 'voz' ? 'O roteiro é o que a voz lê, e a legenda sai com a grafia dele.'
      : 'O roteiro corrige a grafia da legenda onde ele bate com o que foi dito: nomes, marcas, termos em inglês.');
  }
  if (tem.has('tema')) {
    textos.push('O tema vai de contexto para o Gemini: nos cartões, na escolha das cenas e na descrição delas.');
  }
  if (textos.length) t.etapas.push({id: 'texto', titulo: 'O texto', texto: textos.join(' ')});
  t.etapas.push({id: 'imagem', titulo: 'A imagem', texto: imagem});
  // no vídeo único, "Por cima" aparece para pôr o avatar (numa gameplay narrada, por exemplo)
  if (t.modo === 'montagem' || t.escolhePorCima) t.etapas.push({id: 'por-cima', titulo: 'Por cima', texto: porCima});
  t.etapas.push({id: 'fala', titulo: 'A fala', texto: t.modo === 'um'
    ? (doVideo ? 'O som do vídeo: dele saem a legenda e os cortes.' : fala) : fala});
  return t;
}
