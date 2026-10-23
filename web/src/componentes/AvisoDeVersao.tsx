/**
 * O aviso de versão nova (editor/versao.py): o servidor pergunta ao GitHub no máximo uma vez
 * por dia; aqui só aparece o que ele respondeu. "Não avisar mais" fica guardado.
 */
import React, {useEffect, useState} from 'react';
import {api} from '../api';
import type {AvisoDeVersao as Aviso} from '../tipos';

export const AvisoDeVersao: React.FC = () => {
  const [aviso, setAviso] = useState<Aviso | null>(null);
  const [fechado, setFechado] = useState(false);
  useEffect(() => {
    api.versao().then((r) => setAviso(r.aviso)).catch(() => undefined);
  }, []);
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
