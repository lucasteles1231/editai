/**
 * O efeito na voz, no passo 2: os prontos e os seus em pílulas, o "ouvir antes" com 8 s da
 * fala e o estúdio de voz, onde um efeito é montado de ouvido e guardado. O efeito vai como
 * texto, "tom=9,coral=20", o mesmo que o editor lê (editor/efeitos_da_voz.py), e entra
 * depois da transcrição: a legenda continua certa.
 */
import React, {useEffect, useRef, useState} from 'react';
import {api} from '../api';
import type {EfeitoDeVoz, EfeitosDaVoz, Voz} from '../tipos';
import {EstudioDeVoz} from './EstudioDeVoz';

type Props = {
  efeito: string;
  mudar: (efeito: string) => void;
  catalogo: EfeitosDaVoz;
  aoMudarCatalogo: (c: EfeitosDaVoz) => void;
  /** O tratamento da voz escolhido: o "ouvir antes" passa por ele também. */
  tratamento: Voz;
  /** De onde vem a fala ("audio:ID" ou "video:ID"); ``null`` quando ainda não dá para ouvir. */
  fonte: string | null;
  /** Por que não dá para ouvir (quando ``fonte`` é ``null``). */
  semFonte: string;
};

export const EfeitoNaVoz: React.FC<Props> = ({efeito, mudar, catalogo, aoMudarCatalogo, tratamento, fonte, semFonte}) => {
  const [vez, setVez] = useState(0);
  const [ouvido, setOuvido] = useState<{url: string; efeito: string} | null>(null);
  const [estudio, setEstudio] = useState<{efeito: string; editando: EfeitoDeVoz | null} | null>(null);
  const [erro, setErro] = useState('');
  const tocador = useRef<HTMLAudioElement>(null);
  const marcado = catalogo.efeitos.find((e) => e.efeito === efeito) ?? null;

  useEffect(() => {
    if (ouvido) tocador.current?.play().catch(() => undefined);
  }, [ouvido]);

  const ouvir = () => {
    if (!fonte) return;
    setOuvido({url: api.ouvirEfeitoUrl(fonte, efeito, tratamento, vez + 1), efeito});
    setVez(vez + 1);
  };

  const apagar = async (e: EfeitoDeVoz) => {
    setErro('');
    try {
      aoMudarCatalogo((await api.apagarEfeito(e.nome)).efeitos_da_voz);
    } catch (x) {
      setErro((x as Error).message);
    }
  };

  return (
    <div className="efeito-na-voz" aria-label="efeito na voz">
      <span className="rotulo" id="rotulo-efeito">Efeito na voz</span>
      <div className="linha-de-opcoes" role="group" aria-labelledby="rotulo-efeito">
        <button type="button" className="pilula" aria-pressed={!efeito} onClick={() => mudar('')}>Nenhum</button>
        {catalogo.efeitos.map((e) => (e.meu ? (
          <span key={e.nome} className="pilula-sua">
            <button type="button" className="pilula" aria-pressed={marcado?.nome === e.nome} title={e.frase}
              onClick={() => mudar(e.efeito)}>
              {e.titulo} <span className="selo-meu">seu</span>
            </button>
            <button type="button" className="editar-pilula" aria-label={`editar o efeito ${e.titulo} no estúdio`}
              title="Editar no estúdio" onClick={() => setEstudio({efeito: e.efeito, editando: e})}>✎</button>
            <button type="button" className="apagar-pilula" aria-label={`apagar o efeito ${e.titulo}`}
              title="Apagar este efeito" onClick={() => void apagar(e)}>×</button>
          </span>
        ) : (
          <button key={e.nome} type="button" className="pilula" aria-pressed={marcado?.nome === e.nome} title={e.frase}
            onClick={() => mudar(e.efeito)}>{e.titulo}</button>
        )))}
        {efeito && !marcado ? <span className="pilula personalizada" aria-current="true">Personalizado</span> : null}
      </div>
      <small>
        {marcado ? marcado.frase : efeito ? `Montado no estúdio: ${efeito}.` : 'A voz sem efeito.'} O efeito entra
        depois da transcrição, então a legenda continua certa.
      </small>
      <div className="linha-de-opcoes">
        <button type="button" className="botao pequeno" disabled={!fonte} onClick={ouvir}>
          {efeito ? 'Ouvir 8 s com o efeito' : 'Ouvir 8 s'}
        </button>
        <button type="button" className="botao pequeno" onClick={() => setEstudio({efeito, editando: null})}>
          Abrir o estúdio
        </button>
      </div>
      {!fonte ? <small>{semFonte}</small> : null}
      {ouvido ? (
        <div className="ouvir-efeito">
          <audio ref={tocador} controls src={ouvido.url} aria-label="ouvir o efeito na voz" />
          {ouvido.efeito !== efeito ? <small>O efeito mudou: ouça de novo.</small> : null}
        </div>
      ) : null}
      {erro ? <div className="aviso erro">{erro}</div> : null}
      {estudio ? (
        <EstudioDeVoz efeito={estudio.efeito} editando={estudio.editando} catalogo={catalogo}
          aoMudarCatalogo={aoMudarCatalogo} tratamento={tratamento} fonteDoVideo={fonte}
          aoUsar={mudar} aoFechar={() => setEstudio(null)} />
      ) : null}
    </div>
  );
};
