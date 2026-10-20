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

/** Os espaços de cor que o avatar usa de verdade: a pele, o cabelo, os olhos e a roupa sempre;
 *  a barba, os óculos e o acessório só com a parte. */
export function espacosUsados(e: Escolhas): EspacoDeCor[] {
  const usados = new Set<EspacoDeCor>(['pele', 'cabelo', 'olho', 'roupa']);
  for (const c of ESCOLHIDAS) {
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
