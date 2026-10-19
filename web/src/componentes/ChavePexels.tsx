/**
 * A chave do Pexels, no painel de "Antes de começar": ela liga a busca de fotos grátis para o
 * fundo da thumbnail. Como a do Gemini, a chave vai para o servidor local e nunca volta.
 */
import React, {useState} from 'react';
import type {EstadoChave} from '../tipos';

type Props = {
  pexels: EstadoChave;
  aoSalvarChave: (chave: string) => Promise<void>;
  aoApagarChave: () => Promise<void>;
};

export const ChavePexels: React.FC<Props> = ({pexels, aoSalvarChave, aoApagarChave}) => {
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

  return (
    <section className="chave-gemini" aria-label="a chave do Pexels">
      {pexels.configurada ? (
        <div className="linha-de-opcoes chave-ok">
          <small>
            <strong>Pexels ligado</strong> ·{' '}
            {pexels.origem === 'variavel' ? 'chave da variável PEXELS_API_KEY' : `chave ${pexels.final}`}
          </small>
          {pexels.origem === 'arquivo' ? (
            <button type="button" className="botao pequeno"
              onClick={() => void aoApagarChave().catch((x: Error) => setErro(x.message))}>Remover chave</button>
          ) : null}
        </div>
      ) : (
        <>
          <small>
            Liga a busca de fotos grátis para o fundo da thumbnail, na aba Fundo. Criar a chave leva um minuto.
          </small>
          <form className="chave-ia" onSubmit={salvar}>
            <input type="password" autoComplete="off" spellCheck={false} value={chave} data-foco
              placeholder="Cole aqui a sua chave do Pexels" aria-label="chave do Pexels"
              onChange={(e) => setChave(e.target.value)} />
            <button type="submit" className="botao pequeno" disabled={!chave.trim() || salvando}>
              {salvando ? 'Conferindo…' : 'Salvar chave'}
            </button>
          </form>
          <a href="https://www.pexels.com/api/" target="_blank" rel="noreferrer">Pegar uma chave grátis do Pexels</a>
        </>
      )}
      {erro ? <div className="aviso erro">{erro}</div> : null}
      <small className="aviso-ia">A chave fica só neste computador. Só o texto da busca sai dele.</small>
    </section>
  );
};
