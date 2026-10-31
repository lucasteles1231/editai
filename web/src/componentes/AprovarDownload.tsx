/**
 * "Aprovar e baixar": nada baixa sem o ok de quem usa. Quando o servidor responde que falta
 * algo (o Whisper na primeira edição, o auditor das fotos…), esta janela mostra cada coisa
 * com o tamanho, para que serve e a licença. O que tem reserva vem com a caixa marcada e pode
 * ficar de fora; o essencial não. "Agora não" cancela o pedido sem baixar nada; quando tudo o
 * que falta tem reserva, o botão é "Seguir sem baixar", e o pedido segue com a reserva.
 *
 * Fica montada uma vez na página e se registra em ``api.aoPrecisarDeOk``: todo pedido que
 * receber o 409 passa por ela e é refeito com a resposta.
 */
import React, {useEffect, useRef, useState} from 'react';
import {aoPrecisarDeOk, type PedidoDeOk, type RespostaDoOk} from '../api';
import {Dialogo} from './Dialogo';

type Aberto = {pedido: PedidoDeOk; responder: (r: RespostaDoOk) => void};

function legivel(n: number): string {
  for (const [unidade, base] of [['GB', 1e9], ['MB', 1e6], ['KB', 1e3]] as const) {
    if (n >= base) {
      const valor = n / base;
      return `${valor < 10 ? valor.toFixed(1).replace('.', ',') : valor.toFixed(0)} ${unidade}`;
    }
  }
  return `${n} bytes`;
}

export const AprovarDownload: React.FC = () => {
  const [aberto, setAberto] = useState<Aberto | null>(null);
  const [marcados, setMarcados] = useState<Set<string>>(new Set());
  // a resposta sai uma vez só: pelo botão, ou pelo × e pelo Esc ("Agora não")
  const respondido = useRef(false);

  useEffect(() => {
    aoPrecisarDeOk((pedido) => new Promise<RespostaDoOk>((responder) => {
      respondido.current = false;
      setMarcados(new Set(pedido.precisa_de_ok.map((c) => c.id)));
      setAberto({pedido, responder});
    }));
    return () => aoPrecisarDeOk(null);
  }, []);

  if (!aberto) return null;
  const faltam = aberto.pedido.precisa_de_ok;
  const escolhidos = faltam.filter((c) => c.essencial || marcados.has(c.id));
  const bytes = escolhidos.reduce((soma, c) => soma + c.bytes, 0);
  // só com o que tem reserva, não baixar não cancela nada: segue sem eles
  const soOpcionais = faltam.every((c) => !c.essencial);

  const responder = (r: RespostaDoOk) => {
    if (respondido.current) return;
    respondido.current = true;
    aberto.responder(r);
    setAberto(null);
  };
  const aprovar = () => responder({
    aprovados: escolhidos.map((c) => c.id),
    recusados: faltam.filter((c) => !c.essencial && !marcados.has(c.id)).map((c) => c.id),
  });
  const seguirSem = () => responder({aprovados: [], recusados: faltam.map((c) => c.id)});
  const alternar = (id: string) => setMarcados((m) => {
    const novo = new Set(m);
    if (novo.has(id)) novo.delete(id); else novo.add(id);
    return novo;
  });

  return (
    <Dialogo titulo="Antes de seguir" aoFechar={() => responder(null)}>
      <p>
        Para isto, o Editai precisa baixar o que está abaixo. É uma vez só: fica no seu
        computador, e nada mais sai dele por causa disso.
      </p>
      <ul className="a-baixar">
        {faltam.map((c) => (
          <li key={c.id}>
            <label className="interruptor">
              <input type="checkbox" checked={c.essencial || marcados.has(c.id)} disabled={c.essencial}
                onChange={() => alternar(c.id)} />
              <span className="chave" aria-hidden="true" />
              <span className="texto">
                <strong>{c.nome} · {c.tamanho}</strong>
                <small>
                  {c.para_que}.{' '}
                  {c.essencial ? 'Sem ele, não dá para seguir.' : 'Opcional.'}{' '}
                  Licença: <a href={c.link} target="_blank" rel="noopener noreferrer">{c.licenca}</a>.
                </small>
              </span>
            </label>
          </li>
        ))}
      </ul>
      <div className="botoes-do-ok">
        <button type="button" className="botao principal" onClick={aprovar} data-foco>
          {bytes ? `Aprovar e baixar ${legivel(bytes)}` : 'Seguir sem baixar'}
        </button>
        {soOpcionais ? (bytes ? (
          <button type="button" className="botao pequeno" onClick={seguirSem}>Seguir sem baixar</button>
        ) : null) : (
          <button type="button" className="botao pequeno" onClick={() => responder(null)}>Agora não</button>
        )}
      </div>
    </Dialogo>
  );
};
