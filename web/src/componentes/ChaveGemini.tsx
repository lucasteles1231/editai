/**
 * A chave do Gemini, no topo da página: ela liga as ideias de thumbnail, a matriz das cenas e
 * os cartões animados, que ficam em passos diferentes. A chave vai para o servidor local e
 * nunca volta: a página só sabe o fim dela.
 */
import React, {useState} from 'react';
import type {EstadoIa} from '../tipos';

const ONDE_PEGAR = 'https://aistudio.google.com/apikey';

type Props = {
  ia: EstadoIa;
  aoSalvarChave: (chave: string) => Promise<void>;
  aoApagarChave: () => Promise<void>;
};

/** Leva até o campo da chave e põe o foco nele (o PainelIa usa, quando falta a chave). */
export function irParaAChave(): void {
  document.getElementById('chave-gemini')?.scrollIntoView({behavior: 'smooth', block: 'center'});
  document.querySelector<HTMLInputElement>('#chave-gemini input')?.focus({preventScroll: true});
}

export const ChaveGemini: React.FC<Props> = ({ia, aoSalvarChave, aoApagarChave}) => {
  const [chave, setChave] = useState('');
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState('');

  const salvar = async (e: React.FormEvent) => {
    e.preventDefault();
    setSalvando(true);
    setErro('');
    try {
      await aoSalvarChave(chave.trim());
      setChave('');
    } catch (x) {
      setErro((x as Error).message);
    } finally {
      setSalvando(false);
    }
  };

  if (ia.configurada) {
    return (
      <section className="chave-gemini pronta" id="chave-gemini" aria-label="a chave do Gemini">
        <div className="linha-de-opcoes chave-ok">
          <small>
            <strong>Gemini ligado</strong> ·{' '}
            {ia.origem === 'variavel' ? 'chave da variável GEMINI_API_KEY' : ia.falsa ? 'IA de teste (sem rede)'
              : `chave ${ia.final}`}
          </small>
          {ia.origem === 'arquivo' ? (
            <button type="button" className="botao pequeno" onClick={() => void aoApagarChave().catch((x: Error) => setErro(x.message))}>
              Remover chave
            </button>
          ) : null}
        </div>
        {erro ? <div className="aviso erro">{erro}</div> : null}
      </section>
    );
  }

  return (
    <section className="chave-gemini" id="chave-gemini" aria-label="a chave do Gemini">
      <strong>Chave do Gemini <span className="etiqueta">opcional e grátis</span></strong>
      <small>
        Liga as ideias de thumbnail, a matriz da biblioteca de cenas e os cartões animados. Sem ela, todo o resto
        funciona do mesmo jeito.
      </small>
      <form className="chave-ia" onSubmit={salvar}>
        <input type="password" autoComplete="off" spellCheck={false} value={chave}
          placeholder="Cole aqui a sua chave do Gemini" aria-label="chave do Gemini"
          onChange={(e) => setChave(e.target.value)} />
        <button type="submit" className="botao pequeno" disabled={!chave.trim() || salvando}>
          {salvando ? 'Conferindo…' : 'Salvar chave'}
        </button>
      </form>
      {erro ? <div className="aviso erro">{erro}</div> : null}
      <a href={ONDE_PEGAR} target="_blank" rel="noreferrer">Pegar uma chave grátis no Google AI Studio</a>
      <small className="aviso-ia">
        A chave fica só neste computador. Ao usar uma dessas funções, o que ela precisa vai para o Gemini, do Google:
        o texto da fala e quadros pequenos (até 512 px) do vídeo ou das cenas. O vídeo não sai do computador. Na cota
        gratuita, o Google pode usar esse conteúdo para melhorar os produtos dele.
      </small>
    </section>
  );
};
