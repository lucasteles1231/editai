/**
 * O texto do efeito na voz, "tom=9,coral=20", lido e escrito do mesmo jeito que o editor
 * (editor/efeitos_da_voz.py): os zeros saem e a ordem é a dos controles. Assim o efeito
 * escolhido bate, letra por letra, com o de um pronto ou de um seu.
 */
import type {ControleDaVoz} from './tipos';

export type Ajustes = Record<string, number>;

export function lerEfeito(texto: string): Ajustes {
  const ajustes: Ajustes = {};
  for (const parte of texto.split(/[,;\s]+/)) {
    const [chave, valor] = parte.split('=');
    const n = Number(valor);
    if (chave && valor !== undefined && Number.isInteger(n) && n) ajustes[chave.trim().toLowerCase()] = n;
  }
  return ajustes;
}

export function escreverEfeito(ajustes: Ajustes, controles: ControleDaVoz[]): string {
  return controles.filter((c) => ajustes[c.chave]).map((c) => `${c.chave}=${ajustes[c.chave]}`).join(',');
}

/** "+9 semitons", "40%", "−3 dB"; o zero é "—". */
export function comUnidade(valor: number, c: ControleDaVoz): string {
  if (!valor) return '—';
  if (c.unidade === '%') return `${valor}%`;
  const sinal = valor > 0 ? '+' : '−';
  return `${sinal}${Math.abs(valor)} ${c.unidade === 'semitons' && Math.abs(valor) === 1 ? 'semitom' : c.unidade}`;
}
