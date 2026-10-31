/**
 * "Antes de começar (opcional)", logo abaixo do título: um cartão para cada coisa que se
 * configura uma vez e vale para todos os vídeos — a voz sintetizada, o avatar e as chaves do
 * Gemini e do Pexels — e o que está no computador (os modelos baixados, cada um com o "Tirar").
 * Cada cartão diz se já está pronto e abre o próprio painel; nada aqui é obrigatório.
 */
import React, {useEffect} from 'react';
import {api} from '../api';
import {Criador} from '../avatar/Criador';
import {type Configuracao, ouvirConfiguracao} from '../configurar';
import type {AvatarSalvo, Componente, EstadoChave, EstadoDasVozes, EstadoIa} from '../tipos';
import {ChavePexels} from './ChavePexels';
import {Dialogo} from './Dialogo';
import {PainelDaIa} from './PainelDaIa';
import {PainelDaVoz} from './MinhaVoz';
import {NoComputador} from './NoComputador';

type Props = {
  ia: EstadoIa | null;
  aoMudarIa: (e: EstadoIa) => void;
  aoSalvarChave: (chave: string) => Promise<void>;
  aoApagarChave: () => Promise<void>;
  pexels: EstadoChave;
  aoSalvarChavePexels: (chave: string) => Promise<void>;
  aoApagarChavePexels: () => Promise<void>;
  vozes: EstadoDasVozes | null;
  aoMudarVozes: (e: EstadoDasVozes) => void;
  avatares: AvatarSalvo[] | null;
  aoMudarAvatares: (a: AvatarSalvo[]) => void;
  aberto: Configuracao | null;
  abrir: (c: Configuracao | null) => void;
  /** O que o Editai baixou ou pode baixar (``null`` enquanto carrega). */
  componentes: Componente[] | null;
  aoMudarComponentes: (c: Componente[]) => void;
};

function legivel(n: number): string {
  for (const [unidade, base] of [['GB', 1e9], ['MB', 1e6], ['KB', 1e3]] as const) {
    if (n >= base) {
      const valor = n / base;
      return `${valor < 10 ? valor.toFixed(1).replace('.', ',') : valor.toFixed(0)} ${unidade}`;
    }
  }
  return `${n} bytes`;
}

function estadoDosComponentes(c: Componente[] | null): string {
  if (!c) return 'carregando…';
  const baixados = c.filter((x) => x.instalado && !x.a_parte);
  if (!baixados.length) return 'nada baixado';
  const bytes = baixados.reduce((soma, x) => soma + x.bytes, 0);
  return `${baixados.length} ${baixados.length === 1 ? 'modelo' : 'modelos'} · ${legivel(bytes)}`;
}

type Cartao = {
  id: Configuracao;
  titulo: string;
  pronto: boolean;
  estado: string;
  liga: string;
  /** A miniatura do cartão (o avatar). */
  imagem?: string;
};

function estadoDaIa(ia: EstadoIa | null): string {
  if (!ia) return 'carregando…';
  if (ia.local.instalando) return 'instalando a IA local…';
  if (ia.provedor === 'local') return `IA local · ${ia.local.modelo}`;
  if (ia.provedor === 'gemini') return `Gemini · ${ia.origem === 'variavel' ? 'variável' : ia.final}`;
  if (ia.provedor === 'falsa') return 'IA de teste';
  return 'sem IA';
}

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
    {id: 'avatar', titulo: 'Avatar', pronto: Boolean(p.avatares?.length),
      estado: !p.avatares ? 'carregando…' : !p.avatares.length ? 'nenhum'
        : p.avatares.length === 1 ? p.avatares[0].nome : `${p.avatares.length} avatares`,
      liga: 'Você em pixel art, pela sua foto: falando na montagem e na thumbnail.',
      imagem: p.avatares?.length
        ? api.quadroDoAvatarUrl(p.avatares[0].apelido, 'neutro_fechada.png', p.avatares[0].criado) : undefined},
    {id: 'gemini', titulo: 'A IA', pronto: Boolean(p.ia?.pronta), estado: estadoDaIa(p.ia),
      liga: 'O roteiro pelo tema, as cenas, os cartões, a matriz, o avatar pela foto e as ideias de capa: no seu '
        + 'computador (a IA local) ou pelo Gemini, com a chave grátis. As vozes do Gemini pedem a chave.'},
    {id: 'pexels', titulo: 'Chave do Pexels', pronto: p.pexels.configurada,
      estado: p.pexels.configurada ? 'ligado' : 'sem chave',
      liga: 'Fotos grátis para o fundo da thumbnail e para o vídeo só pelo tema.'},
    {id: 'componentes', titulo: 'No computador', pronto: false, estado: estadoDosComponentes(p.componentes),
      liga: 'O que o editor baixou, com o tamanho e a licença. Nada baixa sem o seu ok, e cada um sai quando '
        + 'você quiser.'},
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
            {c.imagem ? <img className="miniatura-do-avatar pixel" src={c.imagem} alt="" /> : null}
            <small>{c.liga}</small>
            <button type="button" className="botao pequeno" onClick={() => abrir(c.id)}>
              {c.pronto || c.id === 'componentes' ? 'Ver' : 'Configurar'}
            </button>
          </article>
        ))}
      </div>
      {aberto ? (
        <Dialogo titulo={aberto.id === 'avatar' ? 'O seu avatar' : aberto.titulo} aoFechar={() => abrir(null)}
          largo={aberto.id === 'avatar'}>
          {aberto.id === 'voz' ? <PainelDaVoz estado={p.vozes} aoMudar={p.aoMudarVozes} /> : null}
          {aberto.id === 'avatar' ? (
            <Criador ia={p.ia} avatares={p.avatares} aoMudarAvatares={p.aoMudarAvatares} />
          ) : null}
          {aberto.id === 'gemini' && p.ia ? (
            <PainelDaIa ia={p.ia} aoMudar={p.aoMudarIa} aoSalvarChave={p.aoSalvarChave}
              aoApagarChave={p.aoApagarChave} />
          ) : null}
          {aberto.id === 'componentes' && p.componentes ? (
            <NoComputador componentes={p.componentes} aoMudar={p.aoMudarComponentes} />
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
