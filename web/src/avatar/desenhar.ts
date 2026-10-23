/**
 * O desenho do avatar: as partes vetorizadas (``editor/recursos/personagem/partes``), pintadas
 * com as cores da pessoa, viram um quadro de pixel art no padrão do personagem
 * (``padrao.json``). Um só desenhista para a prévia e para os quadros que vão ao servidor.
 *
 * Cada camada (o cabelo de trás, o corpo, a cabeça…) é desenhada sozinha na grade de 150 px,
 * sem suavizar, e dentro dela cada peça (``<g data-peca>``: um dedo, uma mecha, o capuz)
 * também. Elas se empilham na ordem do padrão, e o contorno sai da própria pilha: o pixel da
 * borda de uma peça fica preto quando o vizinho é o vazio ou uma peça que está atrás. Por isso
 * as partes são formas chapadas — ninguém desenha o contorno das formas à mão, e ele sai
 * igual em todas; à mão ficam só os traços de dentro (o nariz, as mechas, as dobras). Por
 * fora da silhueta, mais um pixel de contorno (a borda de fora é mais grossa, como no
 * um projeto anterior) e a borda branca de adesivo; por fim, a ampliação para 900 × 900.
 *
 * O volume também sai da pilha, como medido no personagem de um projeto anterior (o rosto dele é quase
 * todo de um tom só): o pixel logo por dentro do contorno escurece (o "aro"), e as peças de
 * mistura (``data-mistura``: a lente dos óculos, a sombra da barba) tingem o que está embaixo
 * em vez de cobrir.
 */
import padraoJson from '../../../editor/recursos/personagem/padrao.json';

// Cada parte é um pedaço separado do build, buscado só quando um quadro precisa dela: a
// biblioteca inteira tem uns 360 KB, e um avatar usa uns 30.
const CARREGADORES = import.meta.glob('../../../editor/recursos/personagem/partes/**/*.svg',
  {query: '?raw', import: 'default'}) as Record<string, () => Promise<string>>;
const PREFIXO = '../../../editor/recursos/personagem/partes/';
const TEXTOS = new Map<string, Promise<string>>();

export const PADRAO = padraoJson;
export type Pose = keyof typeof padraoJson.poses;
export type Boca = 'fechada' | 'meia' | 'aberta';
export const POSES = Object.keys(padraoJson.poses) as Pose[];
export const BOCAS: Boca[] = ['fechada', 'meia', 'aberta'];

export type Cores = {
  pele: string; cabelo: string; sobrancelha: string; barba: string; olho: string;
  roupa: string; roupa2: string; oculos: string; acessorio: string;
};

/** As partes escolhidas (o id de cada categoria; "nenhum" é sem a parte) e as cores. */
export type Escolhas = {
  cabeca: string; cabelo: string; olhos: string; sobrancelhas: string; nariz: string;
  barba: string; oculos: string; roupa: string; acessorio: string;
  cores: Cores;
  /** A roupa de manga curta mostra o antebraço (a cor da pele no lugar da manga). */
  mangaCurta?: boolean;
  /** O conjunto dos braços ("ia" procura ``bracos/ia.<pose>.svg``); vazio, os desenhados. */
  bracos?: string;
  /** "nenhum": a boca já vem na cabeça (o manequim). */
  boca?: string;
};

const GRADE = padraoJson.quadro.grade;
const CORTE = padraoJson.quadro.corte_y;
const CAMADAS = padraoJson.camadas;
const SEM_CONTORNO = new Set(padraoJson.sem_contorno);

// ── as cores ──────────────────────────────────────────────────────────────

type Rgb = [number, number, number];

function rgb(hex: string): Rgb {
  const h = hex.replace('#', '');
  const n = parseInt(h.length === 3 ? h.split('').map((c) => c + c).join('') : h, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function hex([r, g, b]: Rgb): string {
  return `#${[r, g, b].map((x) => Math.round(Math.max(0, Math.min(255, x))).toString(16).padStart(2, '0')).join('')}`;
}

/** Mais escuro (``f`` > 0) ou mais claro (``f`` < 0), puxando um pouco para o quente na
 *  sombra: a sombra chapada cinza deixa a pixel art suja. */
export function tom(cor: string, f: number): string {
  const [r, g, b] = rgb(cor);
  if (f >= 0) return hex([r * (1 - f), g * (1 - f) * 0.97, b * (1 - f) * 0.92]);
  const k = -f;
  return hex([r + (255 - r) * k, g + (255 - g) * k, b + (255 - b) * k]);
}

/** As cores de cada classe que as partes usam: as da pessoa, os tons derivados e as fixas. */
export function paleta(e: Escolhas): Record<string, string> {
  const {cores} = e;
  const s = padraoJson.estilo.sombra;
  const l = padraoJson.estilo.luz;
  const cabelo = cores.cabelo;
  const sobrancelha = cores.sobrancelha || tom(cabelo, 0.45);
  const barba = cores.barba || tom(cabelo, 0.12);
  const p: Record<string, string> = {...padraoJson.estilo.fixas};
  const base: Record<string, string> = {
    pele: cores.pele, cabelo, sobrancelha, barba, olho: cores.olho, roupa: cores.roupa, roupa2: cores.roupa2,
    oculos: cores.oculos, acessorio: cores.acessorio,
  };
  for (const [nome, cor] of Object.entries(base)) {
    p[nome] = cor;
    p[`${nome}-sombra`] = tom(cor, s);
    p[`${nome}-sombra2`] = tom(cor, s * 1.85);
    p[`${nome}-luz`] = tom(cor, -l);
  }
  p['pele-blush'] = tom(cores.pele, 0.1);
  // os traços de dentro da pele (o nariz, a orelha, as dobras da mão): a pele bem escura
  p['pele-linha'] = tom(cores.pele, 0.5);
  // o antebraço: a manga (comprida) ou a pele (manga curta)
  const antebraco = e.mangaCurta ? 'pele' : 'roupa';
  p.antebraco = p[antebraco];
  p['antebraco-sombra'] = p[`${antebraco}-sombra`];
  return p;
}

function estiloDe(p: Record<string, string>): string {
  // "x" pinta o preenchimento; "t-x" é traço (linha) da cor x, sem preenchimento
  return Object.entries(p).map(([nome, cor]) => `.${nome}{fill:${cor}}.t-${nome}{fill:none;stroke:${cor}}`).join('');
}

// ── as partes ─────────────────────────────────────────────────────────────

/** Se a parte existe, pelo caminho dentro de ``partes`` ("cabelo/topete.svg"). */
export function existe(caminho: string): boolean {
  return PREFIXO + caminho in CARREGADORES;
}

/** O texto de uma parte (``null`` se ela não existe), buscado uma vez só. */
export function parte(caminho: string): Promise<string | null> {
  const chave = PREFIXO + caminho;
  const carregar = CARREGADORES[chave];
  if (!carregar) return Promise.resolve(null);
  if (!TEXTOS.has(chave)) TEXTOS.set(chave, carregar());
  return TEXTOS.get(chave)!;
}

/** Os ids de uma categoria que existem em ``partes`` (sem o estado: "olhos/amendoado.aberto"
 *  conta como "amendoado"). */
export function opcoes(categoria: string): string[] {
  const ids = new Set<string>();
  for (const k of Object.keys(CARREGADORES)) {
    if (!k.startsWith(`${PREFIXO}${categoria}/`)) continue;
    ids.add(k.slice(PREFIXO.length + categoria.length + 1).replace(/\.svg$/, '').split('.')[0]);
  }
  return [...ids].sort();
}

/** Uma peça desenhada sozinha: a camada dela (para a ordem), se ela ganha contorno e se ela
 *  tinge o que está embaixo (a lente, a sombra da barba) em vez de cobrir. */
type Grupo = {camada: string; svg: string; contorno: boolean; mistura: boolean; apaga?: boolean;
  /** O chapéu (``data-cobre="cabelo"``): o cabelo só aparece abaixo dele. */
  cobre?: boolean};

/** As camadas do cabelo, que o chapéu corta. */
const CABELO = new Set(['cabelo-tras', 'cabelo-frente', 'sombra-do-cabelo']);

function grupos(texto: string | null): Grupo[] {
  if (!texto) return [];
  const doc = new DOMParser().parseFromString(texto, 'image/svg+xml');
  const ser = new XMLSerializer();
  const saida: Grupo[] = [];
  for (const g of doc.querySelectorAll('g[data-camada]')) {
    const camada = g.getAttribute('data-camada') ?? '';
    if (camada === 'apaga') {
      // o que a pose tira do manequim (os braços de antes): apaga o que está embaixo
      saida.push({camada, svg: ser.serializeToString(g), contorno: false, mistura: false, apaga: true});
      continue;
    }
    // a peça pronta (gerada e vetorizada) já traz o contorno e o volume do desenho
    const contorna = !SEM_CONTORNO.has(camada) && g.getAttribute('data-pronto') !== 'sim';
    // as peças de dentro saem à parte, depois do resto da camada, cada uma com o seu contorno
    const pecas = [...g.querySelectorAll(':scope > g[data-peca]')];
    const base = g.cloneNode(true) as Element;
    base.querySelectorAll(':scope > g[data-peca]').forEach((x) => x.remove());
    if (base.querySelector('path, rect, circle, ellipse, polygon')) {
      saida.push({camada, svg: ser.serializeToString(base), contorno: contorna, mistura: false,
        cobre: g.getAttribute('data-cobre') === 'cabelo'});
    }
    for (const peca of pecas) {
      const mistura = peca.getAttribute('data-mistura') === 'sim';
      saida.push({camada, svg: `<g>${ser.serializeToString(peca)}</g>`, mistura,
        contorno: contorna && !mistura && peca.getAttribute('data-contorno') !== 'nao'});
    }
  }
  return saida;
}

/** O arquivo do estado (``olhos/amendoado.lado.svg``), ou o do estado padrão, ou o sem estado. */
function comEstado(categoria: string, id: string, estado: string, padrao: string): Promise<string | null> {
  if (!id || id === 'nenhum') return Promise.resolve(null);
  const achado = [`${categoria}/${id}.${estado}.svg`, `${categoria}/${id}.${padrao}.svg`, `${categoria}/${id}.svg`]
    .find(existe);
  return achado ? parte(achado) : Promise.resolve(null);
}

/** As camadas de um quadro, na ordem do padrão. */
export async function camadasDoQuadro(e: Escolhas, pose: Pose, boca: Boca): Promise<Grupo[]> {
  const p = padraoJson.poses[pose] as {bracos: string; olhos: string; sobrancelhas: string; boca: string};
  const jaAberta = padraoJson.bocas.ja_aberta.includes(pose);
  const estadoDaBoca = boca === 'fechada' || jaAberta ? p.boca : boca;
  const [cabeca, roupa, ...arquivos] = await Promise.all([
    comEstado('cabeca', e.cabeca, '', ''),
    comEstado('roupa', e.roupa, '', ''),
    comEstado('cabelo', e.cabelo, '', ''),
    comEstado('olhos', e.olhos, p.olhos, 'aberto'),
    comEstado('sobrancelhas', e.sobrancelhas, p.sobrancelhas, 'neutra'),
    comEstado('nariz', e.nariz, '', ''),
    e.boca === 'nenhum' ? null : e.boca ? parte(`boca/${e.boca}.${estadoDaBoca}.svg`) : parte(`boca/${estadoDaBoca}.svg`),
    comEstado('barba', e.barba, '', ''),
    comEstado('oculos', e.oculos, '', ''),
    e.bracos ? parte(`bracos/${e.bracos}.${p.bracos}.svg`) : parte(`bracos/${p.bracos}.svg`),
    comEstado('acessorio', e.acessorio, '', ''),
  ]);
  // a roupa escolhida substitui o corpo (o suéter) que vem com a cabeça do manequim
  const daCabeca = grupos(cabeca).filter((g) => !(roupa && g.camada === 'corpo'));
  const todos = [...daCabeca, ...[roupa, ...arquivos].flatMap(grupos)];
  return CAMADAS.flatMap((c) => todos.filter((g) => g.camada === c));
}

// ── o desenho ─────────────────────────────────────────────────────────────

const cacheDeCamadas = new Map<string, Promise<ImageData>>();

/** As cores fixas que vêm no nome da classe (``fixa-f2a33a``): o bico do pato, a crista da galinha,
 *  o chifre da vaca. Elas não seguem nenhum espaço de cor. */
const FIXA = /\bfixa-([0-9a-f]{6})\b/g;

function rasterizar(svgDoGrupo: string, estiloBase: string): Promise<ImageData> {
  const fixas = new Set([...svgDoGrupo.matchAll(FIXA)].map((m) => m[1]));
  const estilo = estiloBase + [...fixas].map((h) => `.fixa-${h}{fill:#${h}}`).join('');
  const chave = estilo + svgDoGrupo;
  const pronto = cacheDeCamadas.get(chave);
  if (pronto) return pronto;
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${GRADE} ${GRADE}" width="${GRADE}" `
    + `height="${GRADE}" shape-rendering="crispEdges"><style>${estilo}</style>${svgDoGrupo}</svg>`;
  const promessa = new Promise<ImageData>((ok, falha) => {
    const img = new Image();
    const url = URL.createObjectURL(new Blob([svg], {type: 'image/svg+xml'}));
    img.onload = () => {
      const c = document.createElement('canvas');
      c.width = GRADE;
      c.height = GRADE;
      const ctx = c.getContext('2d', {willReadFrequently: true})!;
      ctx.imageSmoothingEnabled = false;
      ctx.drawImage(img, 0, 0, GRADE, GRADE);
      URL.revokeObjectURL(url);
      ok(ctx.getImageData(0, 0, GRADE, GRADE));
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      falha(new Error('Não consegui desenhar uma parte do avatar.'));
    };
    img.src = url;
  });
  cacheDeCamadas.set(chave, promessa);
  if (cacheDeCamadas.size > 600) cacheDeCamadas.delete(cacheDeCamadas.keys().next().value!);
  return promessa;
}

/** As cores de um grupo: só elas valem para encaixar a borda serrilhada que sobrar. */
function coresDoGrupo(svg: string, p: Record<string, string>): Rgb[] {
  const nomes = new Set<string>();
  for (const m of svg.matchAll(/class="([^"]+)"/g)) {
    for (const c of m[1].split(/\s+/)) nomes.add(c.replace(/^t-/, ''));
  }
  return [...nomes].filter((n) => p[n] || /^fixa-[0-9a-f]{6}$/.test(n))
    .map((n) => rgb(p[n] ?? `#${n.slice(5)}`));
}

function maisPerto(r: number, g: number, b: number, cores: Rgb[]): Rgb {
  let melhor = cores[0];
  let menor = Infinity;
  for (const c of cores) {
    const d = (r - c[0]) ** 2 + (g - c[1]) ** 2 + (b - c[2]) ** 2;
    if (d < menor) {
      menor = d;
      melhor = c;
    }
  }
  return melhor;
}

/** O cabelo debaixo do chapéu (``data-cobre="cabelo"``), como o dono pediu: o black power e o
 *  coque não passam por cima do boné ou do gorro, e o que sai pelos lados fica amassado por ele,
 *  não cortado reto.
 *
 *  - **Na largura do chapéu,** o cabelo acima do pixel mais baixo dele some (fica por baixo).
 *  - **Fora dela,** o cabelo de cada lado é achatado inteiro na vertical, em direção à linha mais
 *    baixa dele, até o alto encostar na aba. O formato continua o mesmo, só mais baixo (o black
 *    power vira um tufo redondo saindo de baixo do gorro), com o contorno e a textura dele. Cortar
 *    só as colunas deixava pontas e pixels soltos nas beiradas.
 *
 *  Devolve as imagens das camadas de cabelo trocadas (as outras ficam como estão). */
function amassarCabelo(camadas: Grupo[], imagens: ImageData[]): ImageData[] {
  const fundo = new Int16Array(GRADE).fill(-1);
  camadas.forEach((g, i) => {
    if (!g.cobre) return;
    const d = imagens[i].data;
    for (let x = 0; x < GRADE; x++) {
      for (let y = GRADE - 1; y >= 0; y--) {
        if (d[(y * GRADE + x) * 4 + 3] >= 128) {
          fundo[x] = Math.max(fundo[x], y);
          break;
        }
      }
    }
  });
  let primeira = -1;
  let ultima = -1;
  for (let x = 0; x < GRADE; x++) {
    if (fundo[x] < 0) continue;
    if (primeira < 0) primeira = x;
    ultima = x;
  }
  const cabelo = camadas.map((g) => CABELO.has(g.camada));
  if (primeira < 0 || !cabelo.some(Boolean)) return imagens;
  for (let x = primeira; x <= ultima; x++) if (fundo[x] < 0) fundo[x] = fundo[x - 1];
  // onde há cabelo em cada coluna (todas as camadas dele juntas, para andarem iguais)
  const alto = new Int16Array(GRADE).fill(-1);
  const baixo = new Int16Array(GRADE).fill(-1);
  imagens.forEach((img, i) => {
    if (!cabelo[i]) return;
    for (let k = 0; k < GRADE * GRADE; k++) {
      if (img.data[k * 4 + 3] < 128) continue;
      const x = k % GRADE;
      const y = Math.floor(k / GRADE);
      if (alto[x] < 0 || y < alto[x]) alto[x] = y;
      baixo[x] = Math.max(baixo[x], y);
    }
  });
  // cada lado de fora do chapéu: o quanto ele achata (o alto mais alto vai para logo abaixo da
  // aba, e a linha mais baixa daquele lado fica onde está)
  const achata: {de: number; ate: number; base: number; escala: number}[] = [];
  for (const [borda, passo] of [[primeira, -1], [ultima, 1]] as const) {
    let topo = GRADE;
    let base = -1;
    let de = -1;
    let ate = -1;
    for (let x = borda + passo; x >= 0 && x < GRADE; x += passo) {
      if (alto[x] < 0) continue;
      topo = Math.min(topo, alto[x]);
      base = Math.max(base, baixo[x]);
      if (de < 0) de = x;
      ate = x;
    }
    const aba = fundo[borda] + 1;
    if (base < 0 || topo >= aba || base <= aba) continue;
    achata.push({de: Math.min(de, ate), ate: Math.max(de, ate), base, escala: (base - aba) / (base - topo)});
  }
  // o que as outras camadas desenham (a orelha, o rosto): a "janela" do cabelo em cima deles
  // fica onde está, senão ela desce junto e vira um furo
  const embaixo = new Uint8Array(GRADE * GRADE);
  imagens.forEach((img, i) => {
    if (cabelo[i] || camadas[i].mistura || camadas[i].apaga) return;
    for (let k = 0; k < GRADE * GRADE; k++) if (img.data[k * 4 + 3] >= 128) embaixo[k] = 1;
  });
  return imagens.map((img, i) => {
    if (!cabelo[i]) return img;
    const nova = new ImageData(new Uint8ClampedArray(img.data), GRADE, GRADE);
    for (let x = primeira; x <= ultima; x++) {               // na largura do chapéu: some o de cima
      for (let y = 0; y <= Math.min(fundo[x], GRADE - 1); y++) nova.data[(y * GRADE + x) * 4 + 3] = 0;
    }
    for (const {de, ate, base, escala} of achata) {
      for (let x = de; x <= ate; x++) {
        for (let y = 0; y <= base; y++) {
          const k = (y * GRADE + x) * 4;
          // as linhas de origem que caem nesta: fica a mais alta que aparece (o contorno de cima
          // do cabelo não some no achatamento)
          const de0 = Math.max(0, Math.ceil(base - (base - y + 0.5) / escala));
          const ate0 = Math.min(base, Math.floor(base - (base - y - 0.5) / escala));
          const aqui = img.data[k + 3] >= 128;
          if (!aqui && embaixo[y * GRADE + x] && de0 >= alto[x]) {
            nova.data[k + 3] = 0;                           // a janela da orelha fica
            continue;
          }
          let origem = -1;
          for (let o = de0; o <= ate0; o++) {
            if (img.data[(o * GRADE + x) * 4 + 3] >= 128) {
              origem = o;
              break;
            }
          }
          if (origem < 0 && aqui && de0 >= alto[x]) origem = y; // onde a janela estava, o cabelo de antes
          if (origem < 0) {
            nova.data[k + 3] = 0;
            continue;
          }
          const ko = (origem * GRADE + x) * 4;
          for (let c = 0; c < 4; c++) nova.data[k + c] = img.data[ko + c];
        }
      }
    }
    return nova;
  });
}

/** Um quadro na grade (150 × 150), com o contorno e a borda de adesivo. */
export async function desenharNaGrade(e: Escolhas, pose: Pose, boca: Boca): Promise<ImageData> {
  const p = paleta(e);
  const estilo = estiloDe(p);
  const camadas = await camadasDoQuadro(e, pose, boca);
  const imagens = amassarCabelo(camadas, await Promise.all(camadas.map((g) => rasterizar(g.svg, estilo))));
  const n = GRADE * GRADE;
  const cor = new Uint8ClampedArray(n * 4);
  const dono = new Int16Array(n).fill(-1);     // a camada com contorno que está por cima
  const cheio = new Uint8Array(n);
  imagens.forEach((img, i) => {
    const cores = coresDoGrupo(camadas[i].svg, p);
    const contorna = camadas[i].contorno;
    const d = img.data;
    if (camadas[i].apaga) {
      for (let k = 0; k < n; k++) {
        if (d[k * 4 + 3] < 128) continue;
        cheio[k] = 0;
        dono[k] = -1;
        cor[k * 4 + 3] = 0;
      }
      return;
    }
    if (camadas[i].mistura) {
      // tinge o que já está desenhado, na força do alfa da peça; o vazio continua vazio
      for (let k = 0; k < n; k++) {
        const af = d[k * 4 + 3] / 255;
        if (af < 0.04 || !cheio[k]) continue;
        for (let c = 0; c < 3; c++) cor[k * 4 + c] = Math.round(cor[k * 4 + c] * (1 - af) + d[k * 4 + c] * af);
      }
      return;
    }
    for (let k = 0; k < n; k++) {
      if (d[k * 4 + 3] < 128 || Math.floor(k / GRADE) >= CORTE) continue;
      const [r, g, b] = cores.length ? maisPerto(d[k * 4], d[k * 4 + 1], d[k * 4 + 2], cores)
        : [d[k * 4], d[k * 4 + 1], d[k * 4 + 2]];
      cor[k * 4] = r;
      cor[k * 4 + 1] = g;
      cor[k * 4 + 2] = b;
      cor[k * 4 + 3] = 255;
      cheio[k] = 1;
      if (contorna) dono[k] = i;
    }
  });
  // o contorno: a borda de cada parte, contra o vazio ou contra o que está atrás dela
  const [cr, cg, cb] = rgb(padraoJson.estilo.contorno);
  const contorno = new Uint8Array(n);
  for (let y = 0; y < GRADE; y++) {
    for (let x = 0; x < GRADE; x++) {
      const k = y * GRADE + x;
      if (!cheio[k] || dono[k] < 0) continue;
      for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
        const nx = x + dx;
        const ny = y + dy;
        const fora = nx < 0 || ny < 0 || nx >= GRADE || ny >= GRADE;
        const v = fora ? -1 : ny * GRADE + nx;
        if (fora || !cheio[v] || (dono[v] >= 0 && dono[v] < dono[k])) {
          contorno[k] = 1;
          break;
        }
      }
    }
  }
  for (let k = 0; k < n; k++) {
    if (!contorno[k]) continue;
    cor[k * 4] = cr;
    cor[k * 4 + 1] = cg;
    cor[k * 4 + 2] = cb;
  }
  // o aro: o pixel logo por dentro do contorno, um tom mais escuro (o volume de um projeto anterior)
  const aro = padraoJson.estilo.aro;
  for (let y = 1; y < GRADE - 1; y++) {
    for (let x = 1; x < GRADE - 1; x++) {
      const k = y * GRADE + x;
      if (!cheio[k] || contorno[k] || dono[k] < 0) continue;
      if (contorno[k - 1] || contorno[k + 1] || contorno[k - GRADE] || contorno[k + GRADE]) {
        for (let c = 0; c < 3; c++) cor[k * 4 + c] = Math.round(cor[k * 4 + c] * (1 - aro) * (c === 2 ? 0.94 : 1));
      }
    }
  }
  // por fora da silhueta, mais um pixel de contorno: a borda de fora fica com dois
  const fora: number[] = [];
  for (let y = 0; y < GRADE; y++) {
    for (let x = 0; x < GRADE; x++) {
      const k = y * GRADE + x;
      if (cheio[k]) continue;
      if ((x > 0 && cheio[k - 1]) || (x < GRADE - 1 && cheio[k + 1]) || (y > 0 && cheio[k - GRADE])
        || (y < GRADE - 1 && cheio[k + GRADE])) fora.push(k);
    }
  }
  for (const k of fora) {
    cor[k * 4] = cr;
    cor[k * 4 + 1] = cg;
    cor[k * 4 + 2] = cb;
    cor[k * 4 + 3] = 255;
    cheio[k] = 1;
  }
  // a borda de adesivo: o branco em volta da silhueta
  const raio = padraoJson.estilo.adesivo_px;
  const [ar, ag, ab] = rgb(padraoJson.estilo.adesivo);
  const saida = new Uint8ClampedArray(cor);
  for (let y = 0; y < GRADE; y++) {
    for (let x = 0; x < GRADE; x++) {
      const k = y * GRADE + x;
      if (cheio[k]) continue;
      let perto = false;
      for (let dy = -raio; dy <= raio && !perto; dy++) {
        for (let dx = -raio; dx <= raio && !perto; dx++) {
          if (dx * dx + dy * dy > raio * raio + 1) continue;
          const nx = x + dx;
          const ny = y + dy;
          if (nx >= 0 && ny >= 0 && nx < GRADE && ny < GRADE && cheio[ny * GRADE + nx]) perto = true;
        }
      }
      if (perto) {
        saida[k * 4] = ar;
        saida[k * 4 + 1] = ag;
        saida[k * 4 + 2] = ab;
        saida[k * 4 + 3] = 255;
      }
    }
  }
  return new ImageData(saida, GRADE, GRADE);
}

/** O quadro no tamanho do padrão (900 × 900), ampliado sem suavizar. */
export async function desenharQuadro(e: Escolhas, pose: Pose, boca: Boca,
  lado: number = padraoJson.quadro.lado): Promise<HTMLCanvasElement> {
  const grade = await desenharNaGrade(e, pose, boca);
  const pequeno = document.createElement('canvas');
  pequeno.width = GRADE;
  pequeno.height = GRADE;
  pequeno.getContext('2d')!.putImageData(grade, 0, 0);
  const c = document.createElement('canvas');
  c.width = lado;
  c.height = lado;
  const ctx = c.getContext('2d')!;
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(pequeno, 0, 0, lado, lado);
  return c;
}

/** Um pedaço do quadro (``[x, y, largura, altura]`` em pixels da grade), ampliado sem
 *  suavizar: as miniaturas do criador. */
export async function desenharRecorte(e: Escolhas, pose: Pose, boca: Boca,
  [x, y, w, h]: [number, number, number, number], escala: number): Promise<HTMLCanvasElement> {
  const grade = await desenharNaGrade(e, pose, boca);
  const pequeno = document.createElement('canvas');
  pequeno.width = GRADE;
  pequeno.height = GRADE;
  pequeno.getContext('2d')!.putImageData(grade, 0, 0);
  const c = document.createElement('canvas');
  c.width = w * escala;
  c.height = h * escala;
  const ctx = c.getContext('2d')!;
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(pequeno, x, y, w, h, 0, 0, w * escala, h * escala);
  return c;
}

/** O nome do quadro no pacote: "apontando_lado_meia.png". */
export const nomeDoQuadro = (pose: Pose, boca: Boca) => `${pose}_${boca}.png`;
