/**
 * Os passos 2 a 4: edições, legenda e saída. O 1 (o que você tem) está em ``PassoEnvio.tsx``.
 */
import React, {useRef, useState} from 'react';
import {api} from '../api';
import {apelido} from '../presets';
import {numero} from '../formatar';
import type {
  Edicao, EfeitosDaVoz, EstiloDaLegenda, Estado, FormatoDoQuadro, PorCima, Preset, PresetsImportados, Saida, VideoInfo, Voz,
} from '../tipos';
import {EfeitoNaVoz} from './EfeitoNaVoz';
import {Interruptor} from './Interruptor';

export const Cabeca: React.FC<{n: number; titulo: string; texto: string}> = ({n, titulo, texto}) => (
  <header>
    <span className="numero" aria-hidden="true">{n}</span>
    <div>
      <h2>{titulo}</h2>
      <p>{texto}</p>
    </div>
  </header>
);

// ── 2. Edições ───────────────────────────────────────────────────────────

const VOZES: [Voz, string, string][] = [
  ['original', 'Original', 'A voz como foi gravada.'],
  ['limpa', 'Limpa', 'Tira o grave, o eco do cômodo e o chiado, e deixa cada parte no mesmo volume.'],
  ['estudio', 'Estúdio', 'A limpa, mais o brilho, a compressão e a voz aberta em estéreo (a do preset de notícia).'],
];

export const PassoEdicoes: React.FC<{
  edicao: Edicao; mudar: (p: Partial<Edicao>) => void;
  /** Na montagem, o que vai por cima (e pode mudar de lugar); ``null`` no vídeo único. */
  porCima: PorCima | null;
  presets: Preset[];
  /** O preset que bate com a tela; ``null`` é "Personalizado". */
  marcado: string | null;
  aoEscolherPreset: (p: Preset) => void;
  /** Os presets de quem usa: salvar o que está na tela, apagar e importar. */
  aoSalvarPreset: (titulo: string, frase: string, substituir: boolean) => Promise<void>;
  aoApagarPreset: (p: Preset) => Promise<void>;
  aoImportarPresets: (arquivo: File) => Promise<PresetsImportados>;
  temas: Record<string, string>;
  /** Na montagem, a janela com a câmera vale. */
  naMontagem: boolean;
  /** Os efeitos na voz (os prontos e os seus) e de onde o "ouvir antes" tira a fala. */
  efeitosDaVoz: EfeitosDaVoz;
  aoMudarEfeitos: (c: EfeitosDaVoz) => void;
  fonteDaVoz: {fonte: string | null; motivo: string};
}> = ({edicao, mudar, porCima, presets, marcado, aoEscolherPreset, aoSalvarPreset, aoApagarPreset,
  aoImportarPresets, temas, naMontagem, efeitosDaVoz, aoMudarEfeitos, fonteDaVoz}) => {
  const tocando = useRef<HTMLAudioElement | null>(null);
  const [salvando, setSalvando] = useState<{titulo: string; frase: string; conflito: boolean; erro: string} | null>(
    null);
  const [importado, setImportado] = useState<{texto: string; erro: boolean} | null>(null);
  const salvar = async (substituir: boolean) => {
    if (!salvando) return;
    // O que a página já sabe, ela diz na hora (o servidor confere de novo).
    const nome = apelido(salvando.titulo);
    if (presets.some((p) => !p.meu && (p.nome === nome || apelido(p.titulo) === nome))) {
      setSalvando({...salvando, erro: `“${salvando.titulo.trim()}” é o nome de um preset pronto: escolha outro.`});
      return;
    }
    if (!substituir && presets.some((p) => p.meu && p.nome === nome)) {
      setSalvando({...salvando, conflito: true, erro: ''});
      return;
    }
    try {
      await aoSalvarPreset(salvando.titulo, salvando.frase, substituir);
      setSalvando(null);
    } catch (e) {
      const mensagem = (e as Error).message;
      setSalvando({...salvando, conflito: mensagem.startsWith('Já existe'), erro: mensagem.startsWith('Já existe') ? '' : mensagem});
    }
  };
  const importar = async (arquivo: File) => {
    try {
      const r = await aoImportarPresets(arquivo);
      const partes = [r.entraram.length ? `Entraram: ${r.entraram.join(', ')}.` : 'Nenhum preset entrou.'];
      if (r.recusados.length) partes.push(`Ficaram de fora: ${r.recusados.join('; ')}.`);
      setImportado({texto: partes.join(' '), erro: !r.entraram.length});
    } catch (e) {
      setImportado({texto: (e as Error).message, erro: true});
    }
  };
  const ouvir = () => {
    tocando.current?.pause();
    const som = new Audio(api.somDoTemaUrl(edicao.tema_dos_sons, edicao.volume_dos_sons));
    tocando.current = som;
    som.play().catch(() => undefined);
  };
  return (
    <section className="passo" id="passo-edicoes">
      <Cabeca n={2} titulo="Escolha as edições"
        texto="Comece por um preset e ajuste o que quiser. Tudo é decidido por regras, no seu computador; só os cartões animados, as cenas da biblioteca e os destaques da legenda pedem o Gemini." />
      <div className="presets" role="group" aria-label="presets de edição" data-tour="presets">
        {presets.map((p) => (p.meu ? (
          <div key={p.nome} className="preset-meu">
            <button type="button" className="preset meu" aria-pressed={marcado === p.nome}
              onClick={() => aoEscolherPreset(p)}>
              <strong>{p.titulo} <span className="selo-meu">seu</span></strong>
              <small>{p.frase}</small>
            </button>
            <button type="button" className="apagar-preset" aria-label={`apagar o preset ${p.titulo}`}
              title="Apagar este preset"
              onClick={() => aoApagarPreset(p).catch((e: Error) => setImportado({texto: e.message, erro: true}))}>
              ×
            </button>
          </div>
        ) : (
          <button key={p.nome} type="button" className="preset" aria-pressed={marcado === p.nome}
            onClick={() => aoEscolherPreset(p)}>
            <strong>{p.titulo}</strong>
            <small>{p.frase}</small>
          </button>
        )))}
        <div className={`preset personalizado${marcado === null ? ' marcado' : ''}`}
          aria-current={marcado === null ? 'true' : undefined}>
          <strong>Personalizado</strong>
          <small>Vira este quando você muda algum valor de um preset.</small>
          {marcado === null ? (
            <button type="button" className="botao pequeno salvar-preset" disabled={salvando !== null}
              onClick={() => setSalvando({titulo: '', frase: '', conflito: false, erro: ''})}>
              Salvar como preset
            </button>
          ) : null}
        </div>
      </div>
      {salvando ? (
        <form className="novo-preset" aria-label="salvar como preset" onSubmit={(e) => {
          e.preventDefault();
          void salvar(false);
        }}>
          <label className="campo">
            <span>Nome do preset</span>
            <input type="text" value={salvando.titulo} maxLength={40} autoFocus placeholder="Meu vlog"
              onChange={(e) => setSalvando({...salvando, titulo: e.target.value, conflito: false, erro: ''})} />
          </label>
          <label className="campo">
            <span>Frase (opcional)</span>
            <input type="text" value={salvando.frase} maxLength={160} placeholder="Para que tipo de vídeo ele serve"
              onChange={(e) => setSalvando({...salvando, frase: e.target.value})} />
          </label>
          <small>
            Ele guarda as edições, a saída e o modelo e a cor da thumbnail que estão na tela, e fica só neste
            computador, na pasta do seu usuário.
          </small>
          {salvando.conflito ? (
            <div className="aviso">Já existe um preset seu com esse nome. Substituir pelo que está na tela?</div>
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
      <div className="presets-meus">
        <small>Os seus presets ficam só neste computador.</small>
        {presets.some((p) => p.meu) ? (
          <a className="link" href={api.exportarPresetsUrl()} download="meus-presets.json">Exportar os seus</a>
        ) : null}
        <label className="link">
          Importar
          <input type="file" accept=".json,application/json" hidden aria-label="importar presets"
            onChange={(e) => {
              const f = e.target.files?.[0];
              e.target.value = '';
              if (f) void importar(f);
            }} />
        </label>
      </div>
      {importado ? <div className={`aviso${importado.erro ? ' erro' : ''}`} role="status">{importado.texto}</div> : null}
      <div className="grade" data-tour="interruptores">
        <Interruptor ligado={edicao.cortes} aoMudar={(v) => mudar({cortes: v})} titulo="Cortar silêncios"
          descricao="Tira as pausas longas entre as frases. A legenda acompanha o corte." />
        <Interruptor ligado={edicao.zoom} aoMudar={(v) => mudar({zoom: v})} titulo="Zoom de ênfase"
          descricao="Aproxima e afasta nos cortes, e dá um empurrão nas palavras que saltam." />
        <Interruptor ligado={edicao.adesivos} aoMudar={(v) => mudar({adesivos: v})} titulo="Palavras que saltam"
          descricao="Números e nomes saltam da legenda num adesivo colorido." />
        <Interruptor ligado={edicao.icones} aoMudar={(v) => mudar({icones: v})} titulo="Ícones automáticos"
          descricao="Quando a fala cita “dinheiro”, “celular”, “foguete”… o ícone aparece." />
        {porCima && porCima !== 'nada' ? (
          <Interruptor ligado={edicao.mover} aoMudar={(v) => mudar({mover: v})}
            titulo={porCima === 'personagem' ? 'Mover o personagem' : porCima === 'avatar' ? 'Mover o avatar'
              : 'Mover a pessoa'}
            descricao="Em alguns cortes, vai para um lado, para o meio, para cima, para baixo, para perto ou para longe." />
        ) : null}
        {naMontagem ? (
          <Interruptor ligado={edicao.janela} aoMudar={(v) => mudar({janela: v})} titulo="Janela e câmera"
            descricao="A cena numa janela 16:9 que cresce e encolhe, com a câmera empurrando, e o personagem em pé na borda dela." />
        ) : null}
        <Interruptor ligado={edicao.animacoes} aoMudar={(v) => mudar({animacoes: v})} titulo="Cartões animados"
          descricao="Selo, lista, quadro, enquete, carimbo, número e flash, escritos pelo Gemini na palavra certa. Precisa da chave dele (no topo da página)." />
      </div>
      <div className="campos" data-tour="voz-e-bipe">
        <div className="campo largo">
          <span id="rotulo-voz">Voz</span>
          <div className="linha-de-opcoes" role="group" aria-labelledby="rotulo-voz">
            {VOZES.map(([v, nome]) => (
              <button key={v} type="button" className="pilula" aria-pressed={edicao.voz === v}
                onClick={() => mudar({voz: v})}>{nome}</button>
            ))}
          </div>
          <small>{VOZES.find(([v]) => v === edicao.voz)?.[2]}</small>
        </div>
        <label className="campo largo">
          <span>Bipe nas palavras</span>
          <input type="text" value={edicao.bipe} maxLength={500} placeholder="droga, porcaria, caramba"
            onChange={(e) => mudar({bipe: e.target.value})} />
          <small>Separadas por vírgula. Uma sílaba vira bipe na voz e asteriscos na legenda: “porca**a”.</small>
        </label>
      </div>
      <EfeitoNaVoz efeito={edicao.efeito_da_voz} mudar={(e) => mudar({efeito_da_voz: e})} catalogo={efeitosDaVoz}
        aoMudarCatalogo={aoMudarEfeitos} tratamento={edicao.voz} fonte={fonteDaVoz.fonte} semFonte={fonteDaVoz.motivo} />
      <div className="campos" data-tour="ritmo">
        <label className="campo">
          <span>Ritmo: {numero(edicao.ritmo, 1)}×</span>
          <input type="range" min={0.5} max={2} step={0.1} value={edicao.ritmo}
            onChange={(e) => mudar({ritmo: Number(e.target.value)})} />
          <small>Mais alto: mais adesivos, ícones, zooms e sons, mais perto um do outro.</small>
        </label>
        <label className="campo">
          <span>Pausa máxima: {numero(edicao.pausa_maxima, 2)} s</span>
          <input type="range" min={0.2} max={1.5} step={0.05} value={edicao.pausa_maxima}
            disabled={!edicao.cortes} onChange={(e) => mudar({pausa_maxima: Number(e.target.value)})} />
          <small>Pausas maiores que isto viram corte.</small>
        </label>
        <label className="campo">
          <span>Respiro no corte: {numero(edicao.respiro, 2)} s</span>
          <input type="range" min={0.05} max={0.4} step={0.05} value={edicao.respiro}
            disabled={!edicao.cortes} onChange={(e) => mudar({respiro: Number(e.target.value)})} />
          <small>O silêncio que fica no lugar da pausa cortada.</small>
        </label>
        <label className="campo">
          <span>Zoom: {numero((edicao.nivel_zoom - 1) * 100)}%</span>
          <input type="range" min={1} max={1.3} step={0.01} value={edicao.nivel_zoom}
            disabled={!edicao.zoom} onChange={(e) => mudar({nivel_zoom: Number(e.target.value)})} />
          <small>Quanto a câmera aproxima.</small>
        </label>
        <label className="campo">
          <span>Empurrão do adesivo: {numero(edicao.empurrao * 100)}%</span>
          <input type="range" min={0} max={0.15} step={0.01} value={edicao.empurrao}
            disabled={!edicao.zoom || !edicao.adesivos} onChange={(e) => mudar({empurrao: Number(e.target.value)})} />
          <small>O zoom rápido quando uma palavra salta.</small>
        </label>
        <label className="campo">
          <span>Centro do zoom (altura): {numero(edicao.ancora_y * 100)}%</span>
          <input type="range" min={0.1} max={0.9} step={0.01} value={edicao.ancora_y}
            disabled={!edicao.zoom} onChange={(e) => mudar({ancora_y: Number(e.target.value)})} />
          <small>40% fica no rosto de quem fala para a câmera.</small>
        </label>
      </div>
      <div className="sons" data-tour="sons">
        <div className="grade">
          <Interruptor ligado={edicao.sons} aoMudar={(v) => mudar({sons: v})} titulo="Efeitos sonoros"
            descricao="Um som quando algo aparece e outro quando o zoom troca ou a pessoa muda de lugar." />
          <Interruptor ligado={edicao.sons_por_palavra} aoMudar={(v) => mudar({sons_por_palavra: v})}
            titulo="Sons por palavra" desabilitado={!edicao.sons}
            descricao="“Dinheiro” toca moedas, “errado” uma buzina, “funcionou” um sino." />
          <Interruptor ligado={edicao.som_nos_cortes} aoMudar={(v) => mudar({som_nos_cortes: v})}
            titulo="Som em cada corte" desabilitado={!edicao.sons || !edicao.cortes}
            descricao="Um clique baixo em cada corte, no estilo dos vídeos de jogo." />
        </div>
        <div className="campos">
          <div className="campo">
            <span id="rotulo-tema">Tema dos sons</span>
            <div className="com-botao">
              <select aria-labelledby="rotulo-tema" value={edicao.tema_dos_sons} disabled={!edicao.sons}
                onChange={(e) => mudar({tema_dos_sons: e.target.value})}>
                {Object.entries(temas).map(([nome, titulo]) => <option key={nome} value={nome}>{titulo}</option>)}
              </select>
              <button type="button" className="botao pequeno" onClick={ouvir} disabled={!edicao.sons}>
                Ouvir
              </button>
            </div>
            <small>Sons da Kenney, em domínio público.</small>
          </div>
          <label className="campo">
            <span>Volume dos sons: {numero(edicao.volume_dos_sons * 100)}%</span>
            <input type="range" min={0.3} max={1.5} step={0.05} value={edicao.volume_dos_sons}
              disabled={!edicao.sons} onChange={(e) => mudar({volume_dos_sons: Number(e.target.value)})} />
            <small>A voz manda: os sons ficam sempre por baixo dela.</small>
          </label>
        </div>
      </div>
    </section>
  );
};

// ── 3. Legenda ───────────────────────────────────────────────────────────

/** As larguras de legenda oferecidas (os presets usam 14, 20 e 36). */
const LARGURAS = [10, 12, 14, 16, 18, 20, 24, 28, 32, 36, 42];

const ESTILOS: [EstiloDaLegenda, string, string][] = [
  ['classica', 'Clássica', 'Uma linha por vez, em karaokê: a palavra-chave acende amarela.'],
  ['destaques', 'Destaques', 'Até 4 palavras que entram uma a uma, com os nomes em ciano, as expressões em rosa e '
    + 'a frase de efeito numa pílula amarela. Quem marca é o Gemini; sem ele, os nomes e os números.'],
];

const IDIOMAS: [string, string][] = [['pt', 'Português'], ['en', 'Inglês'], ['es', 'Espanhol'],
  ['fr', 'Francês'], ['it', 'Italiano'], ['de', 'Alemão']];

export const PassoLegenda: React.FC<{
  estado: Estado; edicao: Edicao; saida: Saida;
  mudar: (p: Partial<Edicao>) => void; mudarSaida: (p: Partial<Saida>) => void;
}> = ({estado, edicao, saida, mudar, mudarSaida}) => {
  const modelo = estado.modelos.find((m) => m.nome === edicao.modelo);
  return (
    <section className="passo" id="passo-legenda">
      <Cabeca n={3} titulo="Legenda"
        texto="A fala é transcrita no seu computador pelo Whisper, palavra por palavra." />
      <div className="campos">
        <label className="campo">
          <span>Idioma da fala</span>
          <select value={edicao.idioma} onChange={(e) => mudar({idioma: e.target.value})}>
            {IDIOMAS.map(([c, n]) => <option key={c} value={c}>{n}</option>)}
          </select>
        </label>
        <label className="campo">
          <span>Modelo do Whisper</span>
          <select value={edicao.modelo} onChange={(e) => mudar({modelo: e.target.value})}>
            {estado.modelos.map((m) => (
              <option key={m.nome} value={m.nome}>
                {m.nome} · {m.tamanho}{m.baixado ? ' · baixado' : ''}
              </option>
            ))}
          </select>
          <small>{modelo && !modelo.baixado
            ? `Será baixado na primeira vez (${modelo.tamanho}).`
            : 'small é o equilíbrio; medium erra menos e é mais lento.'}</small>
        </label>
        <label className="campo">
          <span>Tamanho da letra: {numero(edicao.tamanho_legenda * 100)}%</span>
          <input type="range" min={0.6} max={1.6} step={0.05} value={edicao.tamanho_legenda}
            onChange={(e) => mudar({tamanho_legenda: Number(e.target.value)})} />
        </label>
        <div className="campo">
          <span id="rotulo-estilo">Estilo</span>
          <div className="linha-de-opcoes" role="group" aria-labelledby="rotulo-estilo">
            {ESTILOS.map(([v, nome]) => (
              <button key={v} type="button" className="pilula" aria-pressed={edicao.estilo_da_legenda === v}
                onClick={() => mudar({estilo_da_legenda: v})}>{nome}</button>
            ))}
          </div>
          <small>{ESTILOS.find(([v]) => v === edicao.estilo_da_legenda)?.[2]}</small>
        </div>
        <label className="campo">
          <span>Letras por linha</span>
          <select value={edicao.caracteres_por_linha ?? ''} disabled={edicao.estilo_da_legenda !== 'classica'}
            onChange={(e) => mudar({caracteres_por_linha: e.target.value ? Number(e.target.value) : null})}>
            <option value="">Automático</option>
            {LARGURAS.map((n) => <option key={n} value={n}>Até {n}</option>)}
          </select>
          <small>Automático: até 18 em pé e 32 deitado. Menos letras, menos palavras por vez.</small>
        </label>
        <label className="campo texto-falado inteiro">
          <span>O que você falou (opcional)</span>
          <textarea rows={4} value={edicao.texto_falado} maxLength={20000}
            onChange={(e) => mudar({texto_falado: e.target.value})}
            placeholder="Cole aqui o texto que você leu ou o roteiro que seguiu." />
          <small>
            A legenda pega a grafia do texto onde ele bate com o que o Whisper ouviu: o nome do projeto, as marcas, os
            termos em inglês. O que você improvisou fica como foi ouvido, e o que você pulou não entra. Revise o texto:
            um erro de digitação dele vai para a legenda.
          </small>
        </label>
      </div>
      <div className="grade" style={{marginTop: 14}}>
        <Interruptor ligado={saida.srt} aoMudar={(v) => mudarSaida({srt: v})} titulo="Arquivo .srt"
          descricao="A legenda à parte, para subir no YouTube ou editar." />
        <Interruptor ligado={saida.vtt} aoMudar={(v) => mudarSaida({vtt: v})} titulo="Arquivo .vtt"
          descricao="O mesmo, no formato da web." />
      </div>
    </section>
  );
};

// ── 4. Saída ─────────────────────────────────────────────────────────────

const NOMES_FORMATO: Record<string, string> = {mp4: 'MP4', mov: 'MOV', webm: 'WebM', mkv: 'MKV', gif: 'GIF'};
const NOMES_RESOLUCAO: Record<string, string> = {original: 'Original', '2160p': '4K', '1440p': '1440p',
  '1080p': '1080p', '720p': '720p', '480p': '480p'};
const NOMES_QUALIDADE: Record<string, string> = {alta: 'Alta', equilibrada: 'Equilibrada', leve: 'Leve'};

function ladoCurto(video: VideoInfo | null) {
  return video ? Math.min(video.largura, video.altura) : Infinity;
}

const FORMATOS_DO_QUADRO: [FormatoDoQuadro, string][] = [['fundo', 'Igual ao fundo'], ['vertical', 'Em pé (9:16)'],
  ['horizontal', 'Deitado (16:9)'], ['quadrado', 'Quadrado']];

export const PassoSaida: React.FC<{
  estado: Estado; saida: Saida; video: VideoInfo | null; mudar: (p: Partial<Saida>) => void;
  /** Na montagem, o formato do quadro final (o fundo é encaixado nele). */
  quadro?: {valor: FormatoDoQuadro; mudar: (f: FormatoDoQuadro) => void} | null;
}> = ({estado, saida, video, mudar, quadro}) => {
  const formatos = Object.keys(estado.formatos);
  const codecs = estado.formatos[saida.formato]?.codecs ?? [];
  const curto = ladoCurto(video);
  const escolherFormato = (f: string) => {
    const lista = estado.formatos[f]?.codecs ?? [];
    mudar({formato: f, codec: lista.includes(saida.codec) ? saida.codec : (lista[0] ?? ''), audio: ''});
  };
  return (
    <section className="passo" id="passo-saida">
      <Cabeca n={4} titulo="Saída"
        texto="Só aparece o que este computador consegue gravar." />
      {quadro ? (
        <div className="campo">
          <span>Formato do quadro</span>
          <div className="linha-de-opcoes" role="group" aria-label="formato do quadro">
            {FORMATOS_DO_QUADRO.map(([f, nome]) => (
              <button key={f} type="button" className="pilula" aria-pressed={quadro.valor === f}
                onClick={() => quadro.mudar(f)}>{nome}</button>
            ))}
          </div>
          <small>O fundo entra inteiro, e as sobras ficam com ele mesmo, desfocado.</small>
        </div>
      ) : null}
      <div className="campo">
        <span>Formato</span>
        <div className="linha-de-opcoes" role="group" aria-label="formato">
          {formatos.map((f) => (
            <button key={f} type="button" className="pilula" aria-pressed={saida.formato === f}
              onClick={() => escolherFormato(f)}>{NOMES_FORMATO[f] ?? f}</button>
          ))}
        </div>
      </div>
      {saida.formato === 'gif' ? (
        <div className="aviso">GIF sai sem som, com até {estado.gif_max_s} s, 15 quadros por segundo e no máximo 480 px no lado curto.</div>
      ) : null}
      <div className="campos">
        <label className="campo">
          <span>Codec</span>
          <select value={saida.codec || codecs[0]} disabled={codecs.length < 2}
            onChange={(e) => mudar({codec: e.target.value})}>
            {codecs.map((c) => <option key={c} value={c}>{estado.codecs[c] ?? c}</option>)}
          </select>
        </label>
        <label className="campo">
          <span>Resolução</span>
          <select value={saida.resolucao} onChange={(e) => mudar({resolucao: e.target.value})}
            disabled={saida.formato === 'gif'}>
            {estado.resolucoes.map((r) => {
              const alvo = r === 'original' ? 0 : Number(r.replace('p', ''));
              const maior = alvo > curto;
              return (
                <option key={r} value={r} disabled={maior}>
                  {NOMES_RESOLUCAO[r] ?? r}{maior ? ' (maior que o original)' : ''}
                </option>
              );
            })}
          </select>
        </label>
        <label className="campo">
          <span>Quadros por segundo</span>
          <select value={saida.fps} onChange={(e) => mudar({fps: e.target.value})}
            disabled={saida.formato === 'gif'}>
            {estado.fps.map((f) => <option key={f} value={f}>{f === 'original' ? 'Original' : `${f} fps`}</option>)}
          </select>
        </label>
        <label className="campo">
          <span>Qualidade</span>
          <select value={saida.qualidade} onChange={(e) => mudar({qualidade: e.target.value})}>
            {estado.qualidades.map((q) => <option key={q} value={q}>{NOMES_QUALIDADE[q] ?? q}</option>)}
          </select>
          <small>Alta é a melhor imagem; leve é o arquivo menor.</small>
        </label>
      </div>
    </section>
  );
};
