/**
 * A thumbnail com IA, dentro do passo 5: o aviso do que sai do computador e as três ideias,
 * cada uma desenhada pela mesma composição da prévia. A chave do Gemini fica em "Antes de
 * começar" (ChaveGemini): sem ela, este painel abre o painel da chave.
 */
import React from 'react';
import {abrirConfiguracao} from '../configurar';
import {Thumb, type ThumbProps} from '../thumb/Thumb';
import type {EstadoIa, Ideia} from '../tipos';
import {irParaAChave} from './ChaveGemini';
import {Interruptor} from './Interruptor';

type Props = {
  ia: EstadoIa;
  usar: boolean;
  setUsar: (v: boolean) => void;
  /** A edição terminou: já dá para pedir ideias. */
  pronto: boolean;
  pensando: boolean;
  erro: string;
  ideias: Ideia[];
  escolhida: number;
  aoEscolher: (i: number) => void;
  aoPedirOutras: () => void;
  /** As props de cada ideia para a miniatura (null enquanto o recorte dela carrega). */
  propsDaIdeia: (ideia: Ideia) => ThumbProps | null;
  /** O fundo gerado custa dinheiro: só sai com o clique, ideia por ideia. */
  aoGerarFundo: (i: number) => void;
  gerando: number | null;
  pexelsConfigurado: boolean;
};

const FUNDOS: Record<Ideia['fundo'], string> = {
  video: 'fundo: outro quadro do vídeo', desfocado: 'fundo: o vídeo desfocado', cor: 'fundo: cor',
  banco: 'fundo: foto do Pexels', gerado: 'fundo: imagem gerada',
};

const Aviso: React.FC = () => (
  <small className="aviso-ia">
    Ao usar, o texto da fala e 8 quadros pequenos (512 px) vão para o Gemini, do Google. O vídeo
    não sai do computador. Na cota gratuita, o Google pode usar esse conteúdo para melhorar os
    produtos dele.
  </small>
);

export const PainelIa: React.FC<Props> = (p) => {
  if (!p.ia.configurada) {
    return (
      <div className="painel-ia" id="painel-ia">
        <strong>Thumbnail com IA <span className="etiqueta">opcional</span></strong>
        <p>
          Com uma chave do Gemini, a IA lê o que você falou, olha 8 quadros do vídeo e sugere 3
          thumbnails de acordo com o conteúdo: chamada, quadro, cores, ícone e seta.
        </p>
        <div className="linha-de-opcoes">
          <button type="button" className="botao pequeno" onClick={irParaAChave}>
            Colar a chave do Gemini
          </button>
        </div>
        <Aviso />
      </div>
    );
  }

  return (
    <div className="painel-ia" id="painel-ia">
      <Interruptor ligado={p.usar} aoMudar={p.setUsar} titulo="Sugerir thumbnails com IA"
        descricao="Quando a edição terminar, o Gemini sugere 3 ideias de acordo com o que você falou." />
      {p.usar ? (
        <>
          {p.pensando ? <div className="aviso">O Gemini está olhando o vídeo…</div> : null}
          {p.erro ? <div className="aviso erro">{p.erro}</div> : null}
          {p.ideias.length ? (
            <div className="ideias" role="group" aria-label="ideias de thumbnail">
              {p.ideias.map((ideia, i) => {
                const props = p.propsDaIdeia(ideia);
                return (
                  <div key={`${ideia.chamada}-${i}`} className="ideia-cartao">
                    <button type="button" className="ideia" aria-pressed={p.escolhida === i}
                      onClick={() => p.aoEscolher(i)}>
                      <div className="miniatura-ideia">
                        {props ? <Thumb {...props} /> : <div className="carregando-ideia" />}
                      </div>
                      <span>{ideia.ideia || ideia.chamada}</span>
                      <small>{FUNDOS[ideia.fundo]}{ideia.mao !== 'nenhuma' ? ' · mão apontando' : ''}</small>
                    </button>
                    {ideia.fundo === 'gerado' && !ideia.imagem ? (
                      <button type="button" className="botao pequeno" disabled={p.gerando !== null}
                        title={ideia.cena} onClick={() => p.aoGerarFundo(i)}>
                        {p.gerando === i ? 'Gerando…' : 'Gerar fundo · ~US$ 0,04'}
                      </button>
                    ) : null}
                    {ideia.fundo === 'banco' && !ideia.imagem && !p.pexelsConfigurado ? (
                      <small>
                        A foto vem do Pexels:{' '}
                        <button type="button" className="link" onClick={() => abrirConfiguracao('pexels')}>
                          cole a chave do Pexels
                        </button>.
                      </small>
                    ) : null}
                  </div>
                );
              })}
            </div>
          ) : !p.pronto && !p.pensando ? (
            <small>As ideias aparecem aqui quando a edição terminar.</small>
          ) : null}
          {p.pronto ? (
            <button type="button" className="botao pequeno" disabled={p.pensando} onClick={p.aoPedirOutras}>
              {p.ideias.length ? 'Sugerir outras 3' : 'Sugerir com IA'}
            </button>
          ) : null}
          <Aviso />
        </>
      ) : null}
    </div>
  );
};
