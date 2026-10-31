/**
 * O aviso de versão nova (editor/versao.py): o servidor pergunta ao GitHub no máximo uma vez
 * por dia; aqui só aparece o que ele respondeu. "Não avisar mais" fica guardado.
 *
 * Nada sai do computador sem o ok: na primeira vez, a faixa pergunta se pode avisar, e só com o
 * "Avisar" o editor consulta o GitHub.
 */
import React, {useEffect, useState} from 'react';
import {api} from '../api';
import type {AvisoDeVersao as Aviso} from '../tipos';

export const AvisoDeVersao: React.FC = () => {
  const [aviso, setAviso] = useState<Aviso | null>(null);
  const [perguntar, setPerguntar] = useState(false);
  const [fechado, setFechado] = useState(false);
  useEffect(() => {
    api.versao().then((r) => {
      setAviso(r.aviso);
      setPerguntar(r.perguntar);
    }).catch(() => undefined);
  }, []);
  const responder = (sim: boolean) => {
    setPerguntar(false);
    api.permitirVersao(sim).then((r) => setAviso(r.aviso)).catch(() => undefined);
  };
  if (perguntar && !fechado) {
    return (
      <div className="aviso-versao" role="status">
        <span>
          <b>Avisar quando sair versão nova?</b> O editor consulta o GitHub uma vez por dia, sem
          mandar nada seu.
        </span>
        <span className="aviso-versao-acoes">
          <button type="button" className="link" onClick={() => responder(true)}>Avisar</button>
          <button type="button" className="link" onClick={() => responder(false)}>Não</button>
        </span>
      </div>
    );
  }
  if (!aviso || fechado) return null;
  const silenciar = () => {
    setFechado(true);
    api.silenciarVersao().catch(() => undefined);
  };
  return (
    <div className="aviso-versao" role="status">
      <span>
        <b>Saiu o Editai {aviso.nova}</b> (você tem a {aviso.atual}).{' '}
        <a href={aviso.endereco} target="_blank" rel="noreferrer">O que mudou</a>
      </span>
      <span>
        {/* o programa é trocado por baixo: com o Editai aberto, a página perderia os arquivos dela */}
        {aviso.fechar_antes ? 'Para atualizar, feche o Editai e cole no PowerShell: '
          : 'Para atualizar, feche o Editai e rode no terminal: '}
        <code>{aviso.comando}</code>
      </span>
      <span className="aviso-versao-acoes">
        <button type="button" className="link" onClick={silenciar}>Não avisar mais</button>
        <button type="button" className="link" aria-label="Fechar o aviso" onClick={() => setFechado(true)}>Fechar</button>
      </span>
    </div>
  );
};
