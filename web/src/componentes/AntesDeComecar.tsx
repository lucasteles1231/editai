/**
 * "Antes de começar (opcional)", logo abaixo do título: um cartão para cada coisa que se
 * configura uma vez e vale para todos os vídeos — a voz sintetizada e as chaves do Gemini e do
 * Pexels. Cada cartão diz se já está pronto e abre o próprio painel; nada aqui é obrigatório.
 */
import React, {useEffect} from 'react';
import {type Configuracao, ouvirConfiguracao} from '../configurar';
import type {EstadoChave, EstadoDasVozes, EstadoIa} from '../tipos';
import {ChaveGemini} from './ChaveGemini';
import {ChavePexels} from './ChavePexels';
import {Dialogo} from './Dialogo';
import {PainelDaVoz} from './MinhaVoz';

type Props = {
  ia: EstadoIa | null;
  aoSalvarChave: (chave: string) => Promise<void>;
  aoApagarChave: () => Promise<void>;
  pexels: EstadoChave;
  aoSalvarChavePexels: (chave: string) => Promise<void>;
  aoApagarChavePexels: () => Promise<void>;
  vozes: EstadoDasVozes | null;
  aoMudarVozes: (e: EstadoDasVozes) => void;
  aberto: Configuracao | null;
  abrir: (c: Configuracao | null) => void;
};

type Cartao = {
  id: Configuracao;
  titulo: string;
  pronto: boolean;
  estado: string;
  liga: string;
};

function estadoDaVoz(v: EstadoDasVozes | null): [boolean, string] {
  if (!v) return [false, 'carregando…'];
  if (!v.motor.instalado) return [false, 'não instalada'];
  if (!v.vozes.length) return [false, 'nenhuma voz gravada'];
  return [true, v.vozes.length === 1 ? `a voz de ${v.vozes[0].nome}` : `${v.vozes.length} vozes`];
}

export const AntesDeComecar: React.FC<Props> = (p) => {
  const {abrir} = p;
  useEffect(() => ouvirConfiguracao((c) => abrir(c)), [abrir]);

  const [vozPronta, vozEstado] = estadoDaVoz(p.vozes);
  const cartoes: Cartao[] = [
    {id: 'voz', titulo: 'Minha voz', pronto: vozPronta, estado: vozEstado,
      liga: 'A sua própria voz narra um roteiro, na montagem.'},
    {id: 'gemini', titulo: 'Chave do Gemini', pronto: Boolean(p.ia?.configurada),
      estado: !p.ia ? 'carregando…' : p.ia.configurada ? `ligado · ${p.ia.origem === 'variavel' ? 'variável' : p.ia.final}`
        : 'sem chave',
      liga: 'Ideias de capa, cartões animados e a matriz das cenas. Grátis.'},
    {id: 'pexels', titulo: 'Chave do Pexels', pronto: p.pexels.configurada,
      estado: p.pexels.configurada ? 'ligado' : 'sem chave',
      liga: 'Fotos grátis para o fundo da thumbnail.'},
  ];
  const aberto = cartoes.find((c) => c.id === p.aberto);

  return (
    <section className="antes-de-comecar" id="antes-de-comecar" data-tour="antes" aria-label="antes de começar">
      <div className="titulo-da-faixa">
        <strong>Antes de começar</strong> <span className="etiqueta">opcional</span>
      </div>
      <div className="cartoes-de-config">
        {cartoes.map((c) => (
          <article key={c.id} className={`cartao-de-config${c.pronto ? ' pronto' : ''}`} aria-label={c.titulo}>
            <div className="linha-de-opcoes cabeca-do-cartao">
              <strong>{c.titulo}</strong>
              <span className="estado-do-cartao">{c.pronto ? '✓ ' : ''}{c.estado}</span>
            </div>
            <small>{c.liga}</small>
            <button type="button" className="botao pequeno" onClick={() => abrir(c.id)}>
              {c.pronto ? 'Ver' : 'Configurar'}
            </button>
          </article>
        ))}
      </div>
      {aberto ? (
        <Dialogo titulo={aberto.titulo} aoFechar={() => abrir(null)}>
          {aberto.id === 'voz' ? <PainelDaVoz estado={p.vozes} aoMudar={p.aoMudarVozes} /> : null}
          {aberto.id === 'gemini' && p.ia ? (
            <ChaveGemini ia={p.ia} aoSalvarChave={p.aoSalvarChave} aoApagarChave={p.aoApagarChave} />
          ) : null}
          {aberto.id === 'pexels' ? (
            <ChavePexels pexels={p.pexels} aoSalvarChave={p.aoSalvarChavePexels}
              aoApagarChave={p.aoApagarChavePexels} />
          ) : null}
        </Dialogo>
      ) : null}
    </section>
  );
};
