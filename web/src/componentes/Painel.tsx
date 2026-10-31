/**
 * A coluna da direita: o vídeo, o botão de editar, o progresso e o resultado.
 */
import React from 'react';
import {api} from '../api';
import {duracao, numero} from '../formatar';
import type {ParteDaTarefa, Resultado, Tarefa, VideoInfo} from '../tipos';

const NOMES: Record<string, string> = {
  sincronizando: 'Sincronizar o som à parte', limpando: 'Tirar o ruído',
  transcrevendo: 'Transcrever a fala', cortando: 'Cortar os silêncios', escolhendo: 'Escolher o que entra',
  desenhando: 'Desenhar legenda, zoom e ícones', finalizando: 'Finalizar o arquivo',
};

type Props = {
  /** O vídeo mostrado: o único, ou, na montagem, o de fundo. */
  video: VideoInfo | null;
  /** Na montagem, a imagem de quem vai por cima (o recorte da pessoa ou o personagem), na
   *  posição de casa: embaixo no meio em pé, embaixo à direita deitado. */
  porCima?: {url: string; emPe: boolean} | null;
  podeEditar: boolean;
  tarefa: Tarefa | null;
  previa: boolean;
  setPrevia: (v: boolean) => void;
  aoEditar: () => void;
  aoCancelar: () => void;
  erro: string;
  thumbs: {nome: string; url: string; jpgBytes: number}[];
  gerandoThumbs: boolean;
  pastaSaida: string;
  /** Edita de novo com a duração "tudo" (nenhuma frase sai). */
  aoRefazerComTudo: () => void;
};

/** O que a duração escolhida tirou: quantas frases, o alvo e quem escolheu. */
export function textoDaSelecao(s: Resultado['selecao']): string {
  if (!s || !('fora' in s) || !s.fora.length) return '';
  const quem = s.por === 'gemini' || s.por === 'local' ? 'a IA escolheu' : s.por === 'falsa' ? 'a IA de teste escolheu'
    : 'o corte foi no fim, sem a IA, e escolheu';
  const n = s.fora.length;
  return `Para caber em uns ${duracao(s.alvo ?? 0)}, ${quem} as frases que ficam: ${n} ${n === 1 ? 'frase saiu'
    : 'frases saíram'} (de ${duracao(s.antes)} para ${duracao(s.depois)}).`;
}

/** O que o redutor de ruído fez: a força e a folga que o Auto mediu. */
export function textoDoRuido(r: Resultado['ruido']): string {
  if (!r || !('forca' in r)) return '';
  if (r.aviso) return 'O fundo tinha ruído, mas o redutor de ruído não foi baixado: a voz ficou como veio.';
  const quanto = r.forca === 'forte' ? 'todo o ruído' : 'o ruído, de leve,';
  return r.por === 'auto'
    ? `O ruído do fundo saiu: o fundo estava ${Math.round(r.folga_db)} dB abaixo da voz, e o Auto tirou ${quanto}.`
    : `O ruído do fundo saiu: ${r.forca === 'forte' ? 'o forte' : 'o leve'}, como você escolheu.`;
}

/** O atraso do áudio gravado à parte, medido pelo som (ou ajustado à mão). */
export function textoDaSincronia(s: Resultado['sincronia']): string {
  if (!s || !('atraso_s' in s)) return '';
  const ms = Math.round(Math.abs(s.atraso_s) * 1000);
  const quando = s.atraso_s >= 0 ? 'depois' : 'antes';
  const deriva = s.deriva_ppm ? `, e os relógios dos dois andavam ${Math.abs(s.deriva_ppm).toFixed(0)} ppm diferentes` : '';
  return s.confianca === null
    ? `O vídeo foi posto ${ms} ms ${quando} do áudio, como você ajustou.`
    : `Sincronizado pelo som: o vídeo da câmera estava ${ms} ms ${quando} do áudio${deriva}.`;
}

/** Quem escreveu o roteiro (as cenas, os cartões e os destaques da legenda) e quanto. */
export function textoDoRoteiro(r: Resultado['roteiro']): string {
  if (!r || !('por' in r) || !r.por) return '';
  const partes = [r.cenas ? `${r.cenas} cenas` : '', r.cartoes ? `${r.cartoes} cartões` : ''].filter(Boolean);
  const oQue = partes.length ? partes.join(' e ') : 'os destaques da legenda';
  if (r.por === 'gemini') {
    return `Roteiro do Gemini: ${oQue} (${r.pedidos} ${r.pedidos === 1 ? 'pedido' : 'pedidos'} da cota grátis).`;
  }
  if (r.por === 'local') return `Roteiro da IA local: ${oQue} (${r.pedidos} ${r.pedidos === 1 ? 'pedido' : 'pedidos'}).`;
  if (r.por === 'falsa') return `Roteiro da IA de teste: ${oQue}.`;
  if (r.por === 'trechos') return 'As fotos entraram no trecho de cada uma, sem pedido à IA.';
  return r.aviso ? `${r.aviso.charAt(0).toUpperCase()}${r.aviso.slice(1)}.` : '';
}

const SINAL: Record<ParteDaTarefa['estado'], string> = {
  esperando: '·', rodando: '▸', pronto: '✓', pulada: '–', erro: '✕', cancelada: '–',
};

/** Uma parte do processamento com a sua barra e o quanto falta nela. */
const ParteComBarra: React.FC<{parte: ParteDaTarefa}> = ({parte}) => {
  const nome = NOMES[parte.id] ?? parte.nome;
  const valor = parte.estado === 'pronto' ? 'pronto' : parte.estado === 'erro' ? 'erro'
    : parte.estado === 'cancelada' ? 'cancelada' : parte.estado === 'esperando' ? 'na fila'
    : `${numero(parte.fracao * 100)}%`;
  return (
    <li className={`parte ${parte.estado}`}>
      <div className="parte-linha">
        <span aria-hidden="true">{SINAL[parte.estado]}</span>
        <span className="parte-nome">{nome}</span>
        <span className="parte-valor">{valor}</span>
      </div>
      <div className="barra fina" role="progressbar" aria-label={nome} aria-valuemin={0} aria-valuemax={100}
        aria-valuenow={Math.round(parte.fracao * 100)}>
        <div style={{width: `${parte.fracao * 100}%`}} />
      </div>
      {parte.estado === 'rodando' && (parte.detalhe || parte.falta_s) ? (
        <small className="detalhe">
          {parte.detalhe.split('\n')[0]}
          {parte.falta_s ? `${parte.detalhe ? ' · ' : ''}faltam uns ${duracao(parte.falta_s)}` : ''}
        </small>
      ) : null}
    </li>
  );
};

function mostrar(el: HTMLElement | null, block: ScrollLogicalPosition): void {
  const calmo = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  el?.scrollIntoView({behavior: calmo ? 'auto' : 'smooth', block});
}

export const Painel: React.FC<Props> = (p) => {
  const t = p.tarefa;
  const rodando = t?.estado === 'rodando';
  const pronto = t?.estado === 'pronto' && t.resultado;

  // A coluna rola sozinha: ao começar, o progresso aparece inteiro; ao terminar, o
  // resultado sobe para o topo dela (as thumbnails ainda chegam e crescem para baixo).
  const editarRef = React.useRef<HTMLDivElement>(null);
  const resultado = React.useRef<HTMLDivElement>(null);
  const rodandoId = rodando ? t.id : '';
  const prontoId = pronto ? t.id : '';
  React.useEffect(() => {
    if (rodandoId) mostrar(editarRef.current, 'nearest');
  }, [rodandoId]);
  React.useEffect(() => {
    if (prontoId) mostrar(resultado.current, 'start');
  }, [prontoId]);
  const nThumbs = p.thumbs.length;
  // o lugar do vídeo já vem reservado, pelas medidas dele: sem isso, ele crescia quando os
  // metadados chegavam e empurrava o "Editar vídeo" uns 230 px para baixo (no Safari, o clique
  // caía onde o botão estava)
  const proporcao = p.video?.largura && p.video.altura
    ? {aspectRatio: `${p.video.largura} / ${p.video.altura}`} : undefined;
  React.useEffect(() => {
    if (nThumbs) mostrar(resultado.current, 'nearest');
  }, [nThumbs]);

  return (
    <aside className="lateral">
      <div className="painel">
        <h3>{pronto ? 'Vídeo editado' : 'Seu vídeo'}</h3>
        {pronto ? (
          <video key={t.id} className="tela" src={api.arquivoUrl(t.id, 'video', true)} controls playsInline />
        ) : p.video && p.porCima ? (
          <div className={`tela-montada${p.porCima.emPe ? ' em-pe' : ''}`}>
            <video key={p.video.id} className="tela" src={api.videoUrl(p.video.id)} style={proporcao}
              controls playsInline preload="metadata" />
            <img className="por-cima" src={p.porCima.url} alt="" aria-hidden="true" />
          </div>
        ) : p.video ? (
          <video key={p.video.id} className="tela" src={api.videoUrl(p.video.id)} style={proporcao}
            controls playsInline preload="metadata" />
        ) : (
          <div className="vazio">O vídeo aparece aqui depois de enviado.</div>
        )}
      </div>

      <div className="painel" id="botao-editar" ref={editarRef}>
        <button type="button" className="botao principal" disabled={!p.podeEditar || rodando} onClick={p.aoEditar}>
          {rodando ? 'Editando…' : pronto ? 'Editar de novo' : 'Editar vídeo'}
        </button>
        <label className="interruptor" style={{marginTop: 12, border: 'none', padding: '4px 2px'}}>
          <input type="checkbox" checked={p.previa} onChange={(e) => p.setPrevia(e.target.checked)} />
          <span className="chave" aria-hidden="true" />
          <span className="texto">
            <strong>Só os primeiros 15 s</strong>
            <small>Uma prévia rápida para conferir o estilo antes do vídeo inteiro.</small>
          </span>
        </label>
        {p.erro ? <div className="aviso erro">{p.erro}</div> : null}
        {t && t.estado !== 'pronto' ? (
          <div aria-live="polite">
            <div className="barra" role="progressbar" aria-valuemin={0} aria-valuemax={100}
              aria-valuenow={Math.round(t.fracao * 100)}>
              <div style={{width: `${Math.max(3, t.fracao * 100)}%`}} />
            </div>
            <strong>{numero(t.fracao * 100)}%</strong>
            {t.falta_s ? <span> · faltam uns {duracao(t.falta_s)}</span> : null}
            <ul className="partes">
              {(t.partes ?? []).filter((parte) => parte.estado !== 'pulada').map((parte) => (
                <ParteComBarra key={parte.id} parte={parte} />
              ))}
            </ul>
            {t.estado === 'erro' ? <div className="aviso erro">{t.erro}</div> : null}
            {t.estado === 'cancelado' ? <div className="aviso">Edição cancelada.</div> : null}
            {rodando ? (
              <button type="button" className="botao pequeno" style={{marginTop: 10}} onClick={p.aoCancelar}>
                Cancelar
              </button>
            ) : null}
          </div>
        ) : null}
      </div>

      <div className="painel" id="passo-resultado" ref={resultado}>
        <h3>Resultado</h3>
        {pronto ? (
          <>
            <div className="numeros">
              <div><b>{duracao(t.resultado!.duracao_original)}</b><span>antes</span></div>
              <div><b>{duracao(t.resultado!.duracao_final)}</b><span>depois</span></div>
              <div><b>{duracao(t.resultado!.segundos)}</b><span>para editar</span></div>
            </div>
            {textoDoRoteiro(t.resultado!.roteiro) ? (
              <p className="roteiro">{textoDoRoteiro(t.resultado!.roteiro)}</p>
            ) : null}
            {textoDoRuido(t.resultado!.ruido) ? (
              <p className="ruido">{textoDoRuido(t.resultado!.ruido)}</p>
            ) : null}
            {textoDaSincronia(t.resultado!.sincronia) ? (
              <p className="sincronia">{textoDaSincronia(t.resultado!.sincronia)}</p>
            ) : null}
            {textoDaSelecao(t.resultado!.selecao) ? (
              <div className="selecao" aria-label="o que ficou de fora">
                <p>{textoDaSelecao(t.resultado!.selecao)}</p>
                <details>
                  <summary>O que ficou de fora</summary>
                  <ol>
                    {('fora' in t.resultado!.selecao! ? t.resultado!.selecao.fora : []).map((f) => (
                      <li key={f.inicio}><span className="tempo">{duracao(f.inicio)}</span> {f.texto}</li>
                    ))}
                  </ol>
                </details>
                <button type="button" className="botao pequeno" onClick={p.aoRefazerComTudo}>Refazer com tudo</button>
              </div>
            ) : null}
            {t.resultado!.selecao && 'aviso' in t.resultado!.selecao && t.resultado!.selecao.aviso ? (
              <div className="aviso">{t.resultado!.selecao.aviso}</div>
            ) : null}
            <div className="downloads">
              <a className="botao pequeno" href={api.arquivoUrl(t.id, 'video')}>Baixar o vídeo</a>
              {t.resultado!.legendas.map((l) => {
                const ext = l.split('.').pop() ?? '';
                return <a key={l} className="botao pequeno" href={api.arquivoUrl(t.id, ext)}>Legenda .{ext}</a>;
              })}
              <a className="botao pequeno" href={api.arquivoUrl(t.id, 'plano')}>Plano (.json)</a>
              <button type="button" className="botao pequeno rosa" onClick={() => api.abrirPasta()}>Abrir a pasta</button>
            </div>
            {p.gerandoThumbs ? <p>Gerando as thumbnails…</p> : null}
            {p.thumbs.length ? (
              <div className="miniaturas">
                {p.thumbs.map((th) => (
                  <a key={th.nome} href={th.url} title={`baixar ${th.nome}`}>
                    <img src={th.url} alt={`thumbnail ${th.nome}`} />
                  </a>
                ))}
              </div>
            ) : null}
            <p className="salvo-em">
              Salvo em <code>{p.pastaSaida}</code>
            </p>
          </>
        ) : (
          <div className="vazio">Aqui aparecem o vídeo editado, as legendas e as thumbnails — com botão para abrir a pasta.</div>
        )}
      </div>
    </aside>
  );
};
