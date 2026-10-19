/**
 * Uma janela modal da página (o ``<dialog>`` nativo): abre ao montar, fecha pelo ×, pelo Esc
 * ou pelo pai (desmontando). Quem abre guarda o estado; aqui só a moldura.
 */
import React, {useEffect, useId, useRef} from 'react';

type Props = {
  titulo: string;
  aoFechar: () => void;
  /** Mais largo, para o que precisa de espaço (o criador de avatar). */
  largo?: boolean;
  children: React.ReactNode;
};

export const Dialogo: React.FC<Props> = ({titulo, aoFechar, largo, children}) => {
  const dialogo = useRef<HTMLDialogElement>(null);
  const id = useId();
  useEffect(() => {
    const d = dialogo.current;
    if (d && !d.open) d.showModal();
    // o showModal põe o foco no ×; o campo marcado com data-foco (a chave) é o que se usa
    d?.querySelector<HTMLElement>('[data-foco]')?.focus();
  }, []);
  return (
    <dialog ref={dialogo} className={`dialogo${largo ? ' largo' : ''}`} aria-labelledby={id} onClose={aoFechar}>
      <header className="topo-do-dialogo">
        <h2 id={id}>{titulo}</h2>
        <button type="button" className="fechar-dialogo" aria-label={`fechar: ${titulo}`}
          onClick={() => dialogo.current?.close()}>×</button>
      </header>
      <div className="corpo-do-dialogo">{children}</div>
    </dialog>
  );
};
