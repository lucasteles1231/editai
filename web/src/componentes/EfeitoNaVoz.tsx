/**
 * O efeito na voz, no passo 2: os prontos e os seus em pílulas, os controles por grupo (o
 * tom, o caráter, o ambiente e o equalizador), o "ouvir antes" com 8 s da fala e o "salvar
 * como meu efeito". O efeito vai como texto, "tom=9,coral=20", o mesmo que o editor lê
 * (editor/efeitos_da_voz.py), e entra depois da transcrição: a legenda continua certa.
 */
import React, {useEffect, useRef, useState} from 'react';
import {api} from '../api';
import {comUnidade, escreverEfeito, lerEfeito} from '../efeitos';
import {apelido} from '../presets';
import type {EfeitoDeVoz, EfeitosDaVoz, Voz} from '../tipos';

const GRUPOS: [string, string][] = [
  ['tom', 'Tom'], ['carater', 'Caráter'], ['ambiente', 'Ambiente'], ['equalizador', 'Equalizador'],
];

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
  const [salvando, setSalvando] = useState<{titulo: string; conflito: boolean; erro: string} | null>(null);
  const [erro, setErro] = useState('');
  const tocador = useRef<HTMLAudioElement>(null);
  const ajustes = lerEfeito(efeito);
  const marcado = catalogo.efeitos.find((e) => e.efeito === efeito) ?? null;
  const mexidos = Object.keys(ajustes).length;

  useEffect(() => {
    if (ouvido) tocador.current?.play().catch(() => undefined);
  }, [ouvido]);

  const ajustar = (chave: string, valor: number) => mudar(escreverEfeito({...ajustes, [chave]: valor}, catalogo.controles));

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

  const salvar = async (substituir: boolean) => {
    if (!salvando) return;
    // O que a página já sabe, ela diz na hora (o servidor confere de novo).
    const nome = apelido(salvando.titulo);
    if (catalogo.efeitos.some((e) => !e.meu && (e.nome === nome || apelido(e.titulo) === nome))) {
      setSalvando({...salvando, erro: `“${salvando.titulo.trim()}” é o nome de um efeito pronto: escolha outro.`});
      return;
    }
    if (!substituir && catalogo.efeitos.some((e) => e.meu && e.nome === nome)) {
      setSalvando({...salvando, conflito: true, erro: ''});
      return;
    }
    try {
      aoMudarCatalogo((await api.salvarEfeito({titulo: salvando.titulo, efeito}, substituir)).efeitos_da_voz);
      setSalvando(null);
    } catch (x) {
      setSalvando({...salvando, erro: (x as Error).message});
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
        {marcado ? marcado.frase : efeito ? 'Do seu jeito: os ajustes estão abaixo.' : 'A voz sem efeito.'} O efeito
        entra depois da transcrição, então a legenda continua certa.
      </small>
      <details className="ajustes-da-voz" aria-label="ajustes do efeito na voz">
        <summary>Ajustar{mexidos ? ` (${mexidos})` : ''}</summary>
        <div className="grupos-da-voz">
          {GRUPOS.map(([grupo, titulo]) => (
            <fieldset key={grupo}>
              <legend>{titulo}</legend>
              {catalogo.controles.filter((c) => c.grupo === grupo).map((c) => (
                <label key={c.chave} className="controle-da-voz">
                  <span>{c.titulo}</span>
                  <input type="range" min={c.minimo} max={c.maximo} step={1} value={ajustes[c.chave] ?? 0}
                    aria-label={c.titulo} aria-valuetext={comUnidade(ajustes[c.chave] ?? 0, c)}
                    onChange={(ev) => ajustar(c.chave, Number(ev.target.value))} />
                  <output>{comUnidade(ajustes[c.chave] ?? 0, c)}</output>
                </label>
              ))}
            </fieldset>
          ))}
        </div>
        {mexidos ? <button type="button" className="link" onClick={() => mudar('')}>Zerar tudo</button> : null}
      </details>
      <div className="linha-de-opcoes">
        <button type="button" className="botao pequeno" disabled={!fonte} onClick={ouvir}>
          {efeito ? 'Ouvir 8 s com o efeito' : 'Ouvir 8 s'}
        </button>
        {efeito && !marcado && !salvando ? (
          <button type="button" className="botao pequeno" onClick={() => setSalvando({titulo: '', conflito: false, erro: ''})}>
            Salvar como meu efeito
          </button>
        ) : null}
      </div>
      {!fonte ? <small>{semFonte}</small> : null}
      {ouvido ? (
        <div className="ouvir-efeito">
          <audio ref={tocador} controls src={ouvido.url} aria-label="ouvir o efeito na voz" />
          {ouvido.efeito !== efeito ? <small>O efeito mudou: ouça de novo.</small> : null}
        </div>
      ) : null}
      {salvando ? (
        <form className="novo-preset" aria-label="salvar como meu efeito" onSubmit={(e) => {
          e.preventDefault();
          void salvar(false);
        }}>
          <label className="campo">
            <span>Nome do efeito</span>
            <input type="text" value={salvando.titulo} maxLength={40} autoFocus placeholder="Minha voz de rádio"
              onChange={(e) => setSalvando({titulo: e.target.value, conflito: false, erro: ''})} />
          </label>
          <small>Ele guarda os ajustes que estão na tela e fica só neste computador, na pasta do seu usuário.</small>
          {salvando.conflito ? (
            <div className="aviso">Já existe um efeito seu com esse nome. Substituir pelo que está na tela?</div>
          ) : null}
          {salvando.erro ? <div className="aviso erro">{salvando.erro}</div> : null}
          <div className="linha-de-opcoes">
            {salvando.conflito ? (
              <button type="button" className="botao pequeno usar" onClick={() => void salvar(true)}>Substituir</button>
            ) : (
              <button type="submit" className="botao pequeno usar" disabled={!salvando.titulo.trim()}>Salvar</button>
            )}
            <button type="button" className="botao pequeno" onClick={() => setSalvando(null)}>Cancelar</button>
          </div>
        </form>
      ) : null}
      {erro ? <div className="aviso erro">{erro}</div> : null}
    </div>
  );
};
