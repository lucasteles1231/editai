/**
 * Os painéis de "Antes de começar" abertos de qualquer lugar da página: o painel de ideias
 * sem chave, a aba Fundo sem a chave do Pexels, a montagem sem voz gravada. Um evento da
 * janela, para nenhum componente precisar receber o estado da faixa.
 */
export type Configuracao = 'voz' | 'avatar' | 'gemini' | 'pexels';

const EVENTO = 'editai:configurar';

/** Abre o painel ``c`` da faixa "Antes de começar". */
export function abrirConfiguracao(c: Configuracao): void {
  window.dispatchEvent(new CustomEvent<Configuracao>(EVENTO, {detail: c}));
}

/** Chama ``f`` a cada pedido de abrir um painel; devolve como parar de ouvir. */
export function ouvirConfiguracao(f: (c: Configuracao) => void): () => void {
  const ouvir = (e: Event) => f((e as CustomEvent<Configuracao>).detail);
  window.addEventListener(EVENTO, ouvir);
  return () => window.removeEventListener(EVENTO, ouvir);
}
