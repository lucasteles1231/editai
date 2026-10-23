/**
 * O catálogo das partes (``editor/recursos/personagem/catalogo.json``): o que dá para escolher
 * em cada categoria, as cores de cada espaço e o avatar padrão. O mesmo arquivo que o servidor
 * usa para conferir o que o Gemini escolheu pela foto.
 */
import catalogoJson from '../../../editor/recursos/personagem/catalogo.json';
import type {Cores, Escolhas} from './desenhar';

export type Opcao = {id: string; pt: string; en: string; cores: string[]};
export type Categoria = {rotulo: string; nenhum: {pt: string; en: string}; opcoes: Opcao[]};
export type EspacoDeCor = keyof Cores;
type InfoDaCor = {rotulo: string; sugestoes: Record<string, string>; vazia?: string};

export const CATEGORIAS = catalogoJson.categorias as Record<string, Categoria>;
export const CORES = catalogoJson.cores as Record<EspacoDeCor, InfoDaCor>;
/** As categorias que se escolhem, na ordem da página. */
export const ESCOLHIDAS = Object.keys(CATEGORIAS) as ('cabelo' | 'barba' | 'oculos' | 'acessorio' | 'roupa')[];

/** O avatar de partida: o padrão do catálogo com as partes fixas (o manequim, os olhos, a
 *  boca e os braços de cada pose). */
export function escolhasPadrao(): Escolhas {
  const {cores, ...partes} = catalogoJson.padrao;
  return {...(catalogoJson.fixas as Record<string, string>), ...partes, cores: {...cores}} as unknown as Escolhas;
}

/** Um bicho (21/10/2026): a cabeça dele no lugar da do manequim, com os olhos e as bocas
 *  desenhados para ela, e as cores sugeridas. */
export type Bicho = {id: string; pt: string; pelagem: string; olho: string};
export const BICHOS = catalogoJson.bichos as Bicho[];
/** As cores da pelagem: o espaço "pele", com outro nome e outras sugestões. */
export const PELAGEM = catalogoJson.pelagem as InfoDaCor;

export const ehBicho = (e: Escolhas) => BICHOS.some((b) => b.id === e.cabeca);

/** O avatar com a cabeça de um bicho: os olhos e a boca dele, sem as partes da cabeça humana
 *  (o cabelo, a barba, a sobrancelha, os óculos e o acessório não encaixam nela), e as cores
 *  sugeridas. A roupa fica. */
export function comBicho(e: Escolhas, id: string): Escolhas {
  const b = BICHOS.find((x) => x.id === id)!;
  return {...e, cabeca: id, olhos: id, boca: id, sobrancelhas: 'nenhum', cabelo: 'nenhum', barba: 'nenhum',
    oculos: 'nenhum', acessorio: 'nenhum', cores: {...e.cores, pele: b.pelagem, olho: b.olho}};
}

/** De volta à pessoa: a cabeça do manequim, com o cabelo e as cores do avatar padrão. */
export function comPessoa(e: Escolhas): Escolhas {
  if (!ehBicho(e)) return e;
  const padrao = escolhasPadrao();
  return {...e, cabeca: padrao.cabeca, olhos: padrao.olhos, boca: padrao.boca, sobrancelhas: padrao.sobrancelhas,
    cabelo: padrao.cabelo, cores: {...e.cores, pele: padrao.cores.pele, olho: padrao.cores.olho}};
}

/** As categorias que dá para escolher: num bicho, só a roupa. */
export const escolhidasPara = (e: Escolhas) => (ehBicho(e) ? ESCOLHIDAS.filter((c) => c === 'roupa') : ESCOLHIDAS);

/** O rótulo e as sugestões de um espaço de cor: num bicho, a pele é a pelagem. */
export const infoDaCor = (e: Escolhas, espaco: EspacoDeCor) => (espaco === 'pele' && ehBicho(e) ? PELAGEM : CORES[espaco]);

/** Os espaços de cor que o avatar usa de verdade: a pele, o cabelo, os olhos e a roupa sempre;
 *  a barba, os óculos e o acessório só com a parte. Num bicho, sem o cabelo. */
export function espacosUsados(e: Escolhas): EspacoDeCor[] {
  const usados = new Set<EspacoDeCor>(ehBicho(e) ? ['pele', 'olho', 'roupa'] : ['pele', 'cabelo', 'olho', 'roupa']);
  for (const c of escolhidasPara(e)) {
    const id = (e as unknown as Record<string, string>)[c];
    const opcao = CATEGORIAS[c].opcoes.find((o) => o.id === id);
    for (const cor of opcao?.cores ?? []) usados.add(cor as EspacoDeCor);
  }
  return (Object.keys(CORES) as EspacoDeCor[]).filter((c) => usados.has(c));
}

/** O nome de uma opção para a página ("nenhum" diz o que é: "careca", "sem barba"). */
export function nomeDaOpcao(categoria: string, id: string): string {
  const c = CATEGORIAS[categoria];
  if (!c) return id;
  return id === 'nenhum' ? c.nenhum.pt : c.opcoes.find((o) => o.id === id)?.pt ?? id;
}
