/**
 * "No computador": o que o Editai baixou (ou pode baixar), com o tamanho, para que serve e a
 * licença. Cada modelo sai pelo "Tirar", e usar de novo pede o ok de novo. A IA local e as
 * vozes saem pelo cartão de cada uma.
 */
import React, {useEffect, useRef, useState} from 'react';
import {api} from '../api';
import type {Componente} from '../tipos';

type Props = {
  componentes: Componente[];
  aoMudar: (c: Componente[]) => void;
};

/** O cartão onde cada motor à parte se instala e sai. */
const ONDE: Record<string, string> = {'ia-local': 'no cartão A IA', 'voz-local': 'no cartão Minha voz',
  'motor-de-voz': 'no cartão Minha voz'};

export const NoComputador: React.FC<Props> = ({componentes, aoMudar}) => {
  const [tirando, setTirando] = useState('');
  const [erro, setErro] = useState('');
  // ao abrir, a lista de agora (uma vez só): algo pode ter baixado desde que a página abriu
  const mudar = useRef(aoMudar);
  mudar.current = aoMudar;
  useEffect(() => {
    api.componentes().then(({componentes: c}) => mudar.current(c)).catch(() => undefined);
  }, []);

  const tirar = async (c: Componente) => {
    if (!window.confirm(`Tirar ${c.nome} (${c.tamanho}) do computador? Para usar de novo, ele baixa outra vez.`)) {
      return;
    }
    setTirando(c.id);
    setErro('');
    try {
      aoMudar((await api.tirarComponente(c.id)).componentes);
    } catch (e) {
      setErro((e as Error).message);
    } finally {
      setTirando('');
    }
  };

  return (
    <div className="no-computador">
      <p>
        Nada baixa sem o seu ok: o editor pergunta antes, com o tamanho e a licença. Aqui está o
        que ele pode baixar e o que já está no seu computador.
      </p>
      {erro ? <div className="aviso erro">{erro}</div> : null}
      <ul className="componentes">
        {componentes.map((c) => (
          <li key={c.id} className={c.instalado ? 'instalado' : ''}>
            <div className="linha-de-opcoes">
              <strong>{c.nome}</strong>
              <span className="estado-do-cartao">{c.instalado ? `✓ no computador · ${c.tamanho}` : `não baixado · ${c.tamanho}`}</span>
            </div>
            <small>
              {c.para_que}. Licença: <a href={c.link} target="_blank" rel="noopener noreferrer">{c.licenca}</a>.
            </small>
            {c.a_parte ? (
              <small>Instala e sai {ONDE[c.id] ?? 'pelo cartão dele'}.</small>
            ) : c.instalado ? (
              <button type="button" className="botao pequeno" disabled={tirando === c.id}
                onClick={() => void tirar(c)} aria-label={`tirar ${c.nome}`}>
                {tirando === c.id ? 'Tirando…' : 'Tirar'}
              </button>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
};
