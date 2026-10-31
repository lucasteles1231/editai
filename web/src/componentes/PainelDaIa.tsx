/**
 * "A IA", em Antes de começar: quem responde às tarefas de texto e de imagem (o roteiro, as
 * cenas, os cartões, a matriz, o avatar e as ideias de capa), a instalação da IA local e a chave
 * do Gemini. As vozes do Gemini e o fundo gerado precisam da chave, qualquer que seja a
 * principal.
 */
import React, {useEffect, useState} from 'react';
import {api} from '../api';
import type {EstadoIa, PrincipalDaIa} from '../tipos';
import {ChaveGemini} from './ChaveGemini';

const ESPERA_MS = 800;

const PRINCIPAIS: {id: PrincipalDaIa; nome: string; dica: string}[] = [
  {id: 'automatica', nome: 'Automática', dica: 'o Gemini, se houver a chave; sem ela, a IA local'},
  {id: 'gemini', nome: 'Gemini', dica: 'sempre o Gemini, pela internet, com a chave'},
  {id: 'local', nome: 'IA local', dica: 'sempre a IA no seu computador, sem internet'},
];

type Props = {
  ia: EstadoIa;
  aoMudar: (e: EstadoIa) => void;
  aoSalvarChave: (chave: string) => Promise<void>;
  aoApagarChave: () => Promise<void>;
};

const QUEM = {gemini: 'o Gemini', local: 'a IA local', falsa: 'a IA de teste'} as Record<string, string>;

export const PainelDaIa: React.FC<Props> = ({ia, aoMudar, aoSalvarChave, aoApagarChave}) => {
  const [erro, setErro] = useState('');
  const local = ia.local;

  useEffect(() => {
    if (!local.instalando) return undefined;
    const t = setInterval(() => api.estadoDaIa().then(aoMudar).catch(() => undefined), ESPERA_MS);
    return () => clearInterval(t);
  }, [local.instalando, aoMudar]);

  const fazer = (acao: Promise<EstadoIa>) => {
    setErro('');
    acao.then(aoMudar).catch((e) => setErro((e as Error).message));
  };

  return (
    <div className="painel-da-ia">
      <section className="campo" aria-label="quem responde">
        <span>Quem responde</span>
        <div className="pilulas" role="group" aria-label="a IA principal">
          {PRINCIPAIS.map((p) => (
            <button key={p.id} type="button" className="pilula" aria-pressed={ia.principal === p.id} title={p.dica}
              onClick={() => fazer(api.escolherIa(p.id))}>
              {p.nome}
            </button>
          ))}
        </div>
        <small aria-live="polite">
          {ia.pronta ? `Agora responde ${QUEM[ia.provedor] ?? ia.provedor}.`
            : ia.principal === 'local' ? 'Instale a IA local abaixo para ela responder.'
              : ia.principal === 'gemini' ? 'Cole a chave do Gemini abaixo para ele responder.'
                : 'Sem IA: instale a local ou cole a chave do Gemini. O editor funciona sem, só sem as tarefas da IA.'}
          {' '}Se a escolhida falhar, o editor avisa e para: ele não troca de IA sozinho.
        </small>
      </section>

      <section className="campo instalar-ia-local" aria-label="a IA local">
        <span>A IA local ({local.modelo})</span>
        {local.instalado ? (
          <div className="linha-de-opcoes">
            <small>Instalada{local.ocupa ? ` · ${local.ocupa}` : ''}. Roda no seu computador, sem internet e sem chave.</small>
            <button type="button" className="botao pequeno" onClick={() => fazer(api.desinstalarIaLocal())}>
              Desinstalar
            </button>
          </div>
        ) : local.instalando ? (
          <>
            <div className="barra" role="progressbar" aria-valuenow={Math.round(local.fracao * 100)}
              aria-valuemin={0} aria-valuemax={100}><div style={{width: `${Math.max(3, local.fracao * 100)}%`}} /></div>
            <small className="andamento" aria-live="polite">{local.etapa || 'Começando…'}</small>
            <div className="linha-de-opcoes">
              <button type="button" className="botao pequeno" onClick={() => fazer(api.cancelarIaLocal())}>
                Cancelar
              </button>
            </div>
          </>
        ) : (
          <>
            <small>
              Escreve, escolhe as cenas e descreve as imagens no seu computador: nada sai dele. Ocupa {local.espaco} e
              leva {local.tempo}, uma vez só. No texto, ela fica atrás do Gemini: os roteiros saem mais longos, e vale
              revisar os fatos.
            </small>
            <div className="linha-de-opcoes">
              <button type="button" className="botao pequeno usar" onClick={() => fazer(api.instalarIaLocal())}>
                Instalar a IA local
              </button>
            </div>
          </>
        )}
        {local.erro || erro ? <div className="aviso erro">{local.erro || erro}</div> : null}
      </section>

      <section className="campo" aria-label="o Gemini">
        <span>O Gemini</span>
        <ChaveGemini ia={ia} aoSalvarChave={aoSalvarChave} aoApagarChave={aoApagarChave} />
      </section>
    </div>
  );
};
