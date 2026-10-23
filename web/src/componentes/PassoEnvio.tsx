/**
 * O passo 1: o que você tem. A pessoa marca o tema, o roteiro, o áudio, o vídeo completo, o
 * vídeo da pessoa, o personagem e as cenas que tem, e a trilha (``trilha.ts``) diz o caminho
 * do vídeo: de onde vem a imagem, quem vai por cima e de onde vem a fala. Aqui aparecem só os
 * campos que esse caminho pede, etapa por etapa, e "Ajustar as camadas" deixa trocar à mão
 * quem vai por cima e de onde vem a fala.
 */
import React, {useRef, useState} from 'react';
import {api} from '../api';
import {abrirConfiguracao} from '../configurar';
import {opcoesDeFala, semSom} from '../fala';
import {bytes, duracao, numero} from '../formatar';
import {ORDEM, PLATAFORMAS, type Plataforma, juntar} from '../plataformas';
import {MATERIAIS, type Material, type Trilha} from '../trilha';
import type {
  AudioInfo, AvatarSalvo, BibliotecaInfo, CenaDaMatriz, EstadoDasVozes, Fala, MontagemConfig, PersonagemInfo, PorCima,
  VideoInfo,
} from '../tipos';
import {Interruptor} from './Interruptor';
import {MinhaVoz} from './MinhaVoz';
import {Cabeca} from './Passos';
import {RevisaoDaMatriz} from './RevisaoDaMatriz';

/** A matriz na tabela de revisão: as linhas e quem as escreveu. */
export type Revisao = {linhas: CenaDaMatriz[]; por: string; aviso: string; pedidos: number};

/** O que se envia: o vídeo completo, o da pessoa, o personagem, os áudios ou a pasta das cenas. */
export type Envio = 'completo' | 'pessoa' | 'personagem' | 'audio' | 'biblioteca';

/** O custo de recortar a pessoa no vídeo inteiro pelo MODNet, medido num Apple M5 em
 *  04/10/2026: uns 0,07 s por quadro (um vídeo de 27 s a 25 fps levou uns 31 s a mais). */
const CUSTO_DO_RECORTE_POR_QUADRO = 0.07;

/** Quantas palavras por segundo se fala, para estimar a duração do roteiro. */
const PALAVRAS_POR_SEGUNDO = 2.6;

const Soltar: React.FC<{
  rotulo: string; dica: string; aceita: string; progresso: number | null;
  aoEscolher: (arquivo: File) => void; grande?: boolean; nome: string;
  /** Aceita vários de uma vez (os áudios, um por parágrafo). */
  aoEscolherVarios?: (arquivos: File[]) => void;
}> = ({rotulo, dica, aceita, progresso, aoEscolher, grande, nome, aoEscolherVarios}) => {
  const entrada = useRef<HTMLInputElement>(null);
  const [arrastando, setArrastando] = useState(false);
  const escolher = (lista: FileList | null | undefined) => {
    const arquivos = Array.from(lista ?? []);
    if (aoEscolherVarios && arquivos.length) aoEscolherVarios(arquivos);
    else if (arquivos[0]) aoEscolher(arquivos[0]);
  };
  const soltar = (e: React.DragEvent) => {
    e.preventDefault();
    setArrastando(false);
    escolher(e.dataTransfer.files);
  };
  return (
    <div className={`envio${grande ? '' : ' pequena'}${arrastando ? ' arrastando' : ''}`} role="button" tabIndex={0}
      aria-label={rotulo} data-envio={nome}
      onClick={() => entrada.current?.click()}
      onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && entrada.current?.click()}
      onDragOver={(e) => { e.preventDefault(); setArrastando(true); }}
      onDragLeave={() => setArrastando(false)} onDrop={soltar}>
      {grande ? (
        <svg width="46" height="46" viewBox="0 0 24 24" fill="none" stroke="currentColor"
          strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M14 3v4a1 1 0 0 0 1 1h4" />
          <path d="M17 21h-10a2 2 0 0 1 -2 -2v-14a2 2 0 0 1 2 -2h7l5 5v11a2 2 0 0 1 -2 2z" />
          <path d="M10 11l4 2.5l-4 2.5z" />
        </svg>
      ) : null}
      <strong>{progresso !== null ? `Enviando… ${numero(progresso * 100)}%` : rotulo}</strong>
      <small>{dica}</small>
      <input ref={entrada} type="file" accept={aceita} hidden multiple={Boolean(aoEscolherVarios)}
        onChange={(e) => escolher(e.target.files)} />
    </div>
  );
};

/** Os arquivos de uma pasta arrastada, com os das subpastas. O navegador entrega a pasta
 *  como uma "entrada", lida em lotes (de uns 100) até vir vazio. */
async function arquivosDaEntrada(entrada: FileSystemEntry): Promise<File[]> {
  if (entrada.isFile) {
    return new Promise((ok) => (entrada as FileSystemFileEntry).file((f) => ok([f]), () => ok([])));
  }
  if (!entrada.isDirectory) return [];
  const leitor = (entrada as FileSystemDirectoryEntry).createReader();
  const todas: FileSystemEntry[] = [];
  for (;;) {
    const lote = await new Promise<FileSystemEntry[]>((ok) => leitor.readEntries(ok, () => ok([])));
    if (!lote.length) break;
    todas.push(...lote);
  }
  return (await Promise.all(todas.map(arquivosDaEntrada))).flat();
}

/** A pasta das cenas: pelo seletor de pasta ou arrastando. Os vídeos de dentro (e das
 *  subpastas) vão para o editor, e uma matriz que estiver junto também. */
const SoltarPasta: React.FC<{progresso: string | null; aoEscolher: (arquivos: File[]) => void}> = (
  {progresso, aoEscolher},
) => {
  const entrada = useRef<HTMLInputElement>(null);
  const [arrastando, setArrastando] = useState(false);
  const soltar = async (e: React.DragEvent) => {
    e.preventDefault();
    setArrastando(false);
    const entradas = Array.from(e.dataTransfer.items ?? [])
      .map((i) => i.webkitGetAsEntry?.())
      .filter((x): x is FileSystemEntry => Boolean(x));
    const arquivos = entradas.length ? (await Promise.all(entradas.map(arquivosDaEntrada))).flat()
      : Array.from(e.dataTransfer.files);
    if (arquivos.length) aoEscolher(arquivos);
  };
  // O seletor de pasta (``webkitdirectory``) não está nos tipos do React.
  const pasta = {webkitdirectory: '', directory: ''} as React.InputHTMLAttributes<HTMLInputElement>;
  return (
    <div className={`envio pequena${arrastando ? ' arrastando' : ''}`} role="button" tabIndex={0}
      aria-label="Arraste a pasta das cenas" data-envio="cenas"
      onClick={() => entrada.current?.click()}
      onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && entrada.current?.click()}
      onDragOver={(e) => { e.preventDefault(); setArrastando(true); }}
      onDragLeave={() => setArrastando(false)} onDrop={(e) => void soltar(e)}>
      <strong>{progresso ?? 'Arraste a pasta das cenas'}</strong>
      <small>ou clique para escolher · os vídeos e as fotos de dentro, das subpastas também</small>
      <input ref={entrada} type="file" multiple hidden {...pasta}
        onChange={(e) => e.target.files?.length && aoEscolher(Array.from(e.target.files))} />
    </div>
  );
};

const FichaDaBiblioteca: React.FC<{b: BibliotecaInfo}> = ({b}) => (
  <div className="ficha" aria-label="dados da biblioteca de cenas">
    <span className="etiqueta">{b.nome}</span>
    <span className="etiqueta">{b.cenas} cenas{b.fotos ? ` (${b.fotos} foto${b.fotos > 1 ? 's' : ''})` : ''}</span>
    <span className="etiqueta">{duracao(b.duracao)} de cenas</span>
    {b.evitadas ? (
      <span className="etiqueta">
        {b.evitadas} marcada{b.evitadas > 1 ? 's' : ''} “evitar” (fica{b.evitadas > 1 ? 'm' : ''} de fora)
      </span>
    ) : null}
    {b.sem_descricao.length ? (
      <span className="etiqueta" title={b.sem_descricao.join(', ')}>
        {b.sem_descricao.length} clipe{b.sem_descricao.length > 1 ? 's' : ''} sem descrição
      </span>
    ) : null}
    {b.sem_clipe.length ? (
      <span className="etiqueta" title={b.sem_clipe.join(', ')}>
        {b.sem_clipe.length} na matriz sem clipe
      </span>
    ) : null}
  </div>
);

const FichaDoVideo: React.FC<{video: VideoInfo; rotulo?: string}> = ({video, rotulo = 'dados do vídeo'}) => (
  <div className="ficha" aria-label={rotulo}>
    <span className="etiqueta">{video.nome}</span>
    <span className="etiqueta">{video.largura}×{video.altura}</span>
    <span className="etiqueta">{video.vertical ? 'vertical' : 'horizontal'}</span>
    <span className="etiqueta">{duracao(video.duracao)}</span>
    <span className="etiqueta">{numero(video.fps, video.fps % 1 ? 2 : 0)} fps</span>
    <span className="etiqueta">{bytes(video.tamanho_bytes)}</span>
    {!video.tem_audio ? <span className="etiqueta">sem áudio</span> : null}
    {video.tem_alfa ? <span className="etiqueta">com transparência</span> : null}
  </div>
);

export type PropsDoEnvio = {
  /** O caminho do vídeo, montado pelo que foi marcado. */
  trilha: Trilha;
  materiais: ReadonlySet<Material>;
  aoAlternarMaterial: (m: Material) => void;
  tema: string;
  aoMudarTema: (t: string) => void;
  roteiro: string;
  aoMudarRoteiro: (t: string) => void;
  /** "Narrar o roteiro" no lugar do som do vídeo. */
  narrar: boolean;
  aoMudarNarrar: (v: boolean) => void;
  aoEscolherPorCima: (v: 'avatar' | 'nada') => void;
  /** Os vídeos como foram enviados: o completo e o da pessoa. */
  completo: VideoInfo | null;
  daPessoa: VideoInfo | null;
  /** O fundo e quem vai por cima, como a trilha encaixou os vídeos. */
  fundo: VideoInfo | null;
  pessoa: VideoInfo | null;
  /** De onde vem a fala na montagem (a da trilha, ou a escolhida em "Ajustar"). */
  fala: Fala;
  personagem: PersonagemInfo | null;
  /** Os avatares salvos (o cartão "Avatar" de "Antes de começar" cria). */
  avatares: AvatarSalvo[] | null;
  /** Os áudios separados, na ordem em que tocam. */
  audios: AudioInfo[];
  /** A "Minha voz": a narração do roteiro, quando já saiu. */
  narracao: AudioInfo | null;
  aoNarrar: (a: AudioInfo | null) => void;
  vozes: EstadoDasVozes | null;
  aoMudarVozes: (e: EstadoDasVozes) => void;
  /** A biblioteca de cenas, depois da matriz; e o que falta dela enquanto chega. */
  biblioteca: BibliotecaInfo | null;
  /** A pasta já chegou e falta a matriz. */
  faltaMatriz: boolean;
  enviandoBiblioteca: string | null;
  /** A biblioteca aberta no servidor (depois da pasta), para a matriz e as miniaturas. */
  bibliotecaId: string | null;
  /** O Gemini descrevendo as cenas, e a matriz na tabela de revisão. */
  gerandoMatriz: {prontas: number; total: number; pedidos: number} | null;
  revisao: Revisao | null;
  salvandoMatriz: boolean;
  aoGerarMatriz: (assunto: string) => void;
  aoRevisarMatriz: () => void;
  aoUsarMatriz: (linhas: CenaDaMatriz[]) => void;
  aoFecharRevisao: () => void;
  montagem: MontagemConfig;
  mudarMontagem: (p: Partial<MontagemConfig>) => void;
  progresso: Record<Envio, number | null>;
  erro: Record<Envio, string>;
  aoEscolher: (qual: Envio, arquivo: File) => void;
  aoEscolherAudios: (arquivos: File[]) => void;
  aoEscolherPasta: (arquivos: File[]) => void;
  aoEscolherMatriz: (arquivo: File) => void;
  aoTirarAudio: () => void;
  recorte: {baixado: boolean; tamanho: string};
  /** Onde o vídeo vai ser postado, as recomendadas pelo formato dele e os avisos. */
  plataformas: Plataforma[];
  recomendadas: Plataforma[];
  aoAlternarPlataforma: (p: Plataforma) => void;
  avisosDaPlataforma: string[];
};

const Aviso: React.FC<{texto: string}> = ({texto}) => (texto ? <div className="aviso erro">{texto}</div> : null);

const NOMES_DA_FALA: Record<Fala, string> = {fundo: 'O vídeo de fundo', pessoa: 'O vídeo da pessoa',
  audio: 'Áudio separado', voz: 'Minha voz (de um roteiro)', cenas: 'Das cenas'};
const POR_CIMA: [PorCima, string][] = [['pessoa', 'Vídeo da pessoa'], ['avatar', 'Meu avatar'],
  ['personagem', 'Personagem animado'], ['nada', 'Nada']];
/** O texto da etapa "Por cima" quando a escolha em "Ajustar" não é a da trilha. */
const TEXTO_DO_POR_CIMA: Record<PorCima, string> = {
  pessoa: 'Você, recortado do vídeo da pessoa.', avatar: 'O seu avatar, mudando de pose a cada frase.',
  personagem: 'O personagem, mexendo a boca quando a voz fala.',
  nada: 'Ninguém: só a imagem, com a legenda e as animações.',
};

/** "Das cenas": os vídeos da biblioteca que têm som. Cada clique marca o próximo número (a
 *  ordem em que o som toca); clicar de novo tira, e os outros andam. */
const CenasDoAudio: React.FC<{
  biblioteca: BibliotecaInfo; bibliotecaId: string; escolhidas: string[];
  aoMudar: (escolhidas: string[]) => void;
}> = ({biblioteca, bibliotecaId, escolhidas, aoMudar}) => {
  if (!biblioteca.com_som.length) {
    return <small>Nenhum vídeo da biblioteca tem som: escolha outra fonte para o áudio.</small>;
  }
  const alternar = (arquivo: string) => aoMudar(escolhidas.includes(arquivo)
    ? escolhidas.filter((a) => a !== arquivo) : [...escolhidas, arquivo]);
  return (
    <div className="cenas-do-audio" role="group" aria-label="as cenas de onde vem o som">
      {biblioteca.com_som.map((c) => {
        const ordem = escolhidas.indexOf(c.arquivo);
        return (
          <button key={c.arquivo} type="button" className="cena-do-audio" aria-pressed={ordem >= 0}
            aria-label={`${c.arquivo}${ordem >= 0 ? `, ${ordem + 1}ª` : ''}`} onClick={() => alternar(c.arquivo)}>
            <img src={api.quadroDaCenaUrl(bibliotecaId, c.arquivo)} alt="" loading="lazy" />
            {ordem >= 0 ? <span className="ordem">{ordem + 1}</span> : null}
            <small>{c.arquivo} · {duracao(c.duracao)}</small>
          </button>
        );
      })}
    </div>
  );
};

/** Sem matriz (ou para trocar a que veio): o Gemini descreve as cenas, e a pessoa revisa. O
 *  tema, se veio, já é o assunto. */
const GerarMatriz: React.FC<PropsDoEnvio> = (p) => {
  const [assunto, setAssunto] = useState<string | null>(null);
  const g = p.gerandoMatriz;
  const valor = assunto ?? (p.materiais.has('tema') ? p.tema : '');
  return (
    <div className="gerar-matriz">
      <label className="campo">
        <span>{p.biblioteca ? 'Ou gere uma nova com o Gemini' : 'Sem matriz? O Gemini descreve as cenas'}</span>
        <input type="text" value={valor} maxLength={200} disabled={Boolean(g)}
          placeholder="do que são as cenas (opcional): trailers do GTA 6"
          onChange={(e) => setAssunto(e.target.value)} />
        <small>
          Ele vê 3 quadros de cada clipe, 12 clipes por pedido da cota grátis, e escreve a descrição, as
          categorias, a energia e a monetização. Você revisa numa tabela antes de usar. Sem a chave (no topo da página), sai
          um rascunho com o nome de cada arquivo.
        </small>
      </label>
      <div className="linha-de-opcoes">
        <button type="button" className="botao pequeno" disabled={Boolean(g)}
          onClick={() => p.aoGerarMatriz(valor)}>
          {g ? 'Gerando…' : p.biblioteca ? 'Gerar de novo' : 'Gerar a matriz'}
        </button>
        {p.biblioteca ? (
          <button type="button" className="botao pequeno" disabled={Boolean(g)} onClick={p.aoRevisarMatriz}>
            Revisar a matriz
          </button>
        ) : null}
      </div>
      {g ? (
        <small className="andamento" aria-live="polite">
          Descrevendo {g.prontas} de {g.total} cenas… ({g.pedidos} {g.pedidos === 1 ? 'pedido' : 'pedidos'} ao Gemini)
        </small>
      ) : null}
    </div>
  );
};

/** O campo de um vídeo (o completo ou o da pessoa), onde a trilha encaixou ele. */
const CampoDoVideo: React.FC<PropsDoEnvio & {qual: 'completo' | 'pessoa'; grande?: boolean; rotulo: string;
  dica: string; rotuloDaFicha: string}> = (p) => {
  const v = p.qual === 'completo' ? p.completo : p.daPessoa;
  return (
    <>
      <Soltar grande={p.grande} nome={p.qual} rotulo={v ? `Trocar: ${p.rotulo.toLowerCase()}` : p.rotulo} dica={p.dica}
        aceita="video/*,.mkv,.mov,.webm" progresso={p.progresso[p.qual]} aoEscolher={(f) => p.aoEscolher(p.qual, f)} />
      <Aviso texto={p.erro[p.qual]} />
      {v ? <FichaDoVideo video={v} rotulo={p.rotuloDaFicha} /> : null}
    </>
  );
};

/** O tema e o roteiro, quando marcados. Narrado, o roteiro é escrito na etapa da fala, junto
 *  da voz. */
const CamposDoTexto: React.FC<PropsDoEnvio> = (p) => {
  const palavras = p.roteiro.trim() ? p.roteiro.trim().split(/\s+/).length : 0;
  return (
    <>
      {p.materiais.has('tema') ? (
        <label className="campo">
          <span>O tema</span>
          <input type="text" value={p.tema} maxLength={200} aria-label="o tema"
            placeholder="do que é o vídeo: por que o céu é azul" onChange={(e) => p.aoMudarTema(e.target.value)} />
        </label>
      ) : null}
      {p.materiais.has('roteiro') && p.fala !== 'voz' ? (
        <label className="campo">
          <span>O roteiro</span>
          <textarea rows={5} value={p.roteiro} maxLength={20000} aria-label="o roteiro"
            placeholder="Cole aqui o texto do vídeo." onChange={(e) => p.aoMudarRoteiro(e.target.value)} />
          <small>
            {palavras} palavras · uns {duracao(palavras / PALAVRAS_POR_SEGUNDO)} de fala.{' '}
            <label className="link">
              Abrir um .txt
              <input type="file" accept=".txt,text/plain" hidden aria-label="abrir o roteiro de um arquivo"
                onChange={(e) => e.target.files?.[0]?.text().then(p.aoMudarRoteiro)} />
            </label>
          </small>
        </label>
      ) : null}
    </>
  );
};

const CamposDaImagem: React.FC<PropsDoEnvio> = (p) => {
  const t = p.trilha;
  if (t.modo === 'um') {
    const qual = t.completo === 'unico' ? 'completo' : 'pessoa';
    return <CampoDoVideo {...p} qual={qual} grande rotulo="Arraste o vídeo aqui"
      dica="ou clique para escolher · MP4, MOV, MKV, WebM…" rotuloDaFicha="dados do vídeo" />;
  }
  if (p.montagem.fonteDoFundo === 'cenas') {
    return (
      <>
        <small>A pasta com os clipes e a matriz que descreve cada um (o <code>cenas.json</code>).</small>
        <SoltarPasta progresso={p.enviandoBiblioteca} aoEscolher={p.aoEscolherPasta} />
        {p.faltaMatriz || p.biblioteca ? (
          <Soltar nome="matriz" rotulo={p.biblioteca ? 'Trocar a matriz' : 'Agora, a matriz'}
            dica="o cenas.json: uma lista com o arquivo e a descrição de cada cena" aceita=".json,application/json"
            progresso={null} aoEscolher={p.aoEscolherMatriz} />
        ) : null}
        {p.faltaMatriz || p.biblioteca ? <GerarMatriz {...p} /> : null}
        <Aviso texto={p.erro.biblioteca} />
        {p.biblioteca ? <FichaDaBiblioteca b={p.biblioteca} /> : null}
        {p.revisao && p.bibliotecaId ? (
          <RevisaoDaMatriz biblioteca={p.bibliotecaId} linhas={p.revisao.linhas} por={p.revisao.por}
            aviso={p.revisao.aviso} pedidos={p.revisao.pedidos} salvando={p.salvandoMatriz}
            aoUsar={p.aoUsarMatriz} aoFechar={p.aoFecharRevisao} />
        ) : null}
      </>
    );
  }
  if (t.completo === 'fundo' || t.daPessoa === 'fundo') {
    const qual = t.completo === 'fundo' ? 'completo' : 'pessoa';
    return <CampoDoVideo {...p} qual={qual} rotulo={qual === 'completo' ? 'Arraste o vídeo completo' : 'Arraste o vídeo da pessoa'}
      dica="a tela gravada, o jogo, os slides, você falando · MP4, MOV, MKV, WebM…" rotuloDaFicha="dados do fundo" />;
  }
  return null;
};

const CamposDoPorCima: React.FC<PropsDoEnvio> = (p) => {
  const m = p.montagem;
  const t = p.trilha;
  const custo = p.pessoa ? p.pessoa.duracao * p.pessoa.fps * CUSTO_DO_RECORTE_POR_QUADRO : 0;
  const escolha = t.escolhePorCima && (m.porCima === 'avatar' || m.porCima === 'nada') ? (
    <div className="linha-de-opcoes" role="group" aria-label="quem vai por cima">
      <button type="button" className="pilula" aria-pressed={m.porCima === 'avatar'}
        onClick={() => p.aoEscolherPorCima('avatar')}>Meu avatar</button>
      <button type="button" className="pilula" aria-pressed={m.porCima === 'nada'}
        onClick={() => p.aoEscolherPorCima('nada')}>Ninguém</button>
    </div>
  ) : null;
  if (m.porCima === 'pessoa') {
    const qual = t.completo === 'pessoa' ? 'completo' : 'pessoa';
    return (
      <>
        <CampoDoVideo {...p} qual={qual} rotulo={qual === 'completo' ? 'Arraste o vídeo completo' : 'Arraste o vídeo da pessoa'}
          dica="você falando · MP4, MOV, WebM…" rotuloDaFicha="dados do vídeo da pessoa" />
        {p.pessoa ? (
          <div className="campo">
            <span>Tirar o fundo da pessoa</span>
            <div className="linha-de-opcoes" role="group" aria-label="como tirar o fundo da pessoa">
              <button type="button" className="pilula" aria-pressed={m.recorte === 'transparente'}
                disabled={!p.pessoa.tem_alfa} onClick={() => p.mudarMontagem({recorte: 'transparente'})}>
                Já vem sem fundo
              </button>
              <button type="button" className="pilula" aria-pressed={m.recorte === 'modnet'}
                onClick={() => p.mudarMontagem({recorte: 'modnet'})}>Recortar com o MODNet</button>
            </div>
            <small className="custo">
              {m.recorte === 'transparente'
                ? 'O arquivo tem transparência: o recorte é o dele, sem custo nenhum.'
                : `Recorta o vídeo inteiro no seu computador: uns ${duracao(Math.max(5, custo))} a mais num `
                  + 'MacBook M5.'
                  + (p.recorte.baixado ? '' : ` Na primeira vez, o editor baixa o modelo (${p.recorte.tamanho}).`)
                  + (p.pessoa.tem_alfa ? ''
                    : ' Para não esperar, exporte o vídeo já sem fundo, em WebM VP9 ou MOV ProRes 4444.')}
            </small>
          </div>
        ) : null}
      </>
    );
  }
  if (m.porCima === 'personagem') {
    return (
      <>
        <Soltar nome="personagem" rotulo="Arraste o personagem" dica="GIF, PNG animado ou WebP, em loop"
          aceita="image/gif,image/png,image/webp,.gif,.png,.webp,.apng" progresso={p.progresso.personagem}
          aoEscolher={(f) => p.aoEscolher('personagem', f)} />
        <Aviso texto={p.erro.personagem} />
        {p.personagem ? (
          <div className="personagem">
            <img src={api.personagemArquivoUrl(p.personagem.id)} alt={`o personagem ${p.personagem.nome}`} />
            <div className="ficha" aria-label="dados do personagem">
              <span className="etiqueta">{p.personagem.nome}</span>
              <span className="etiqueta">{p.personagem.largura}×{p.personagem.altura}</span>
              <span className="etiqueta">{p.personagem.quadros} quadros</span>
              <span className="etiqueta">{duracao(p.personagem.duracao)} em loop</span>
              <span className="etiqueta">{p.personagem.tem_alfa ? 'transparente' : 'com fundo'}</span>
            </div>
            {!p.personagem.tem_alfa ? (
              <Interruptor ligado={m.tirarFundo && p.personagem.fundo_de_cor} desabilitado={!p.personagem.fundo_de_cor}
                aoMudar={(v) => p.mudarMontagem({tirarFundo: v})} titulo="Tirar o fundo de cor dele"
                descricao={p.personagem.fundo_de_cor ? 'Os quatro cantos têm a mesma cor, e ela some.'
                  : 'Os cantos têm cores diferentes: não dá para saber qual é o fundo.'} />
            ) : null}
          </div>
        ) : null}
      </>
    );
  }
  if (m.porCima === 'avatar') {
    return (
      <>
        {escolha}
        {!p.avatares?.length ? (
          <div className="sem-avatar">
            <small>Você ainda não tem um avatar. Ele é feito uma vez, pela sua foto, e fala por você: a pose
              muda a cada frase e a boca abre nas sílabas.</small>
            <button type="button" className="botao pequeno" onClick={() => abrirConfiguracao('avatar')}>
              Criar o meu avatar
            </button>
          </div>
        ) : (
          <>
            <div className="linha-de-opcoes avatares-da-montagem" role="group" aria-label="qual avatar">
              {p.avatares.map((a) => {
                const escolhido = (m.avatar ?? p.avatares![0].apelido) === a.apelido;
                return (
                  <button key={a.apelido} type="button" className="pilula com-imagem" aria-pressed={escolhido}
                    onClick={() => p.mudarMontagem({avatar: a.apelido})}>
                    <img className="pixel" src={api.quadroDoAvatarUrl(a.apelido, 'neutro_fechada.png', a.criado)}
                      alt="" width={32} height={32} />
                    {a.nome}
                  </button>
                );
              })}
              <button type="button" className="botao pequeno" onClick={() => abrirConfiguracao('avatar')}>
                Criar ou ajustar
              </button>
            </div>
            <small>A pose muda a cada frase (pergunta pensando, "você" apontando, número com o dedo para cima…)
              e a boca abre nas sílabas da voz. Do lado direito da tela, ele vira para o meio.</small>
          </>
        )}
      </>
    );
  }
  return escolha;
};

const CamposDaFala: React.FC<PropsDoEnvio> = (p) => {
  const m = p.montagem;
  const t = p.trilha;
  const narrar = t.podeNarrar ? (
    <Interruptor ligado={p.narrar} aoMudar={p.aoMudarNarrar} titulo="Narrar o roteiro"
      descricao="A narração entra no lugar do som do vídeo: a legenda e os cortes saem dela." />
  ) : null;
  if (t.modo === 'um') return narrar;
  const fala = p.fala;
  const mudos = [semSom(p.fundo) ? 'o vídeo de fundo' : '', m.porCima === 'pessoa' && semSom(p.pessoa) ? 'o vídeo da pessoa' : '']
    .filter(Boolean);
  const nenhumSom = fala !== 'audio' && fala !== 'voz' && fala !== 'cenas'
    && semSom(fala === 'fundo' ? p.fundo : p.pessoa);
  return (
    <>
      {narrar}
      {nenhumSom || mudos.length ? (
        <small>
          {nenhumSom ? 'Nenhum dos vídeos tem som: sem um áudio separado, o vídeo sai mudo, sem cortes e sem legenda.' : ''}
          {mudos.length && !nenhumSom ? ` Sem som: ${mudos.join(' e ')}.` : ''}
        </small>
      ) : null}
      {fala === 'audio' ? (
        <>
          {p.audios.length ? (
            <div className="ficha" aria-label="os áudios separados">
              {p.audios.map((a, i) => (
                <span key={a.id} className="etiqueta">{p.audios.length > 1 ? `${i + 1}. ` : ''}{a.nome} · {duracao(a.duracao)}</span>
              ))}
              <button type="button" className="botao pequeno" onClick={p.aoTirarAudio}>
                {p.audios.length > 1 ? 'Trocar os áudios' : 'Trocar o áudio'}
              </button>
            </div>
          ) : null}
          <Soltar nome="audio" rotulo={p.audios.length ? 'Juntar mais áudios' : 'Arraste o áudio (ou vários)'}
            dica="MP3, WAV, M4A… Vários (um por parágrafo) tocam na ordem do nome, 0,3 s entre eles."
            aceita="audio/*,.mp3,.wav,.m4a" progresso={p.progresso.audio}
            aoEscolher={(f) => p.aoEscolherAudios([f])} aoEscolherVarios={p.aoEscolherAudios} />
        </>
      ) : fala === 'voz' ? <MinhaVoz estado={p.vozes} aoMudar={p.aoMudarVozes} narracao={p.narracao}
        aoNarrar={p.aoNarrar} roteiro={p.roteiro} aoMudarRoteiro={p.aoMudarRoteiro} />
        : fala === 'cenas' ? (p.biblioteca && p.bibliotecaId ? (
          <CenasDoAudio biblioteca={p.biblioteca} bibliotecaId={p.bibliotecaId} escolhidas={m.cenasDoAudio}
            aoMudar={(cenasDoAudio) => p.mudarMontagem({cenasDoAudio})} />
        ) : <small>Envie a pasta das cenas e a matriz: os vídeos com som aparecem aqui.</small>) : null}
      <Aviso texto={p.erro.audio} />
    </>
  );
};

/** Quem vai por cima e de onde vem a fala, à mão. Vale até mudar o que foi marcado. */
const AjustarAsCamadas: React.FC<PropsDoEnvio> = (p) => (
  <details className="ajustar-camadas" data-tour="ajustar">
    <summary>Ajustar as camadas</summary>
    <div className="campo">
      <span>Por cima</span>
      <div className="linha-de-opcoes" role="group" aria-label="o que vai por cima">
        {POR_CIMA.map(([v, nome]) => (
          <button key={v} type="button" className="pilula" aria-pressed={p.montagem.porCima === v}
            onClick={() => p.mudarMontagem({porCima: v})}>{nome}</button>
        ))}
      </div>
    </div>
    <div className="campo">
      <span>A fala vem de</span>
      <div className="linha-de-opcoes" role="group" aria-label="de onde vem o áudio">
        {opcoesDeFala(p.montagem).map((f) => {
          const mudo = f === 'fundo' ? semSom(p.fundo) : f === 'pessoa' ? semSom(p.pessoa) : false;
          return (
            <button key={f} type="button" className="pilula" aria-pressed={p.fala === f} disabled={mudo}
              title={mudo ? 'este vídeo não tem som' : undefined} onClick={() => p.mudarMontagem({fala: f})}>
              {NOMES_DA_FALA[f]}
            </button>
          );
        })}
      </div>
    </div>
    <small>O que você escolher aqui vale até mudar o que você tem, lá em cima.</small>
  </details>
);

/** Onde o vídeo vai ser postado: decide o formato da thumbnail e, na montagem, o do vídeo. */
const OndePostar: React.FC<PropsDoEnvio> = (p) => {
  const emPe = p.recomendadas.length > 0 && !p.recomendadas.includes('youtube');
  return (
    <div className="plataformas" id="plataformas">
      <strong>Onde você vai postar?</strong>
      <div className="linha-de-opcoes" role="group" aria-label="onde você vai postar">
        {ORDEM.map((pl) => (
          <button key={pl} type="button" className="pilula" aria-pressed={p.plataformas.includes(pl)}
            onClick={() => p.aoAlternarPlataforma(pl)}>
            {PLATAFORMAS[pl].nome}
            {p.recomendadas.includes(pl) ? <>{' '}<span className="recomendado">recomendado</span></> : null}
          </button>
        ))}
      </div>
      <small>
        {p.recomendadas.length
          ? `Para um vídeo ${emPe ? 'em pé' : 'deitado'}, o editor recomenda ${juntar(p.recomendadas.map((x) => PLATAFORMAS[x].nome))}. `
          : 'Envie o vídeo, e o editor recomenda pelo formato dele. '}
        Dá para marcar várias: a thumbnail sai no formato de cada uma{p.trilha.modo === 'montagem'
          ? ', e o vídeo montado também' : ''}.
      </small>
      {p.plataformas.includes('shorts') ? <small>{PLATAFORMAS.shorts.nota}</small> : null}
      {p.avisosDaPlataforma.map((a) => <div key={a} className="aviso">{a}</div>)}
    </div>
  );
};

export const PassoEnvio: React.FC<PropsDoEnvio> = (p) => {
  const t = p.trilha;
  const campos: Record<string, React.ReactNode> = {
    texto: <CamposDoTexto {...p} />, imagem: <CamposDaImagem {...p} />, 'por-cima': <CamposDoPorCima {...p} />,
    fala: <CamposDaFala {...p} />,
  };
  return (
    <section className="passo" id="passo-envio">
      <Cabeca n={1} titulo="O que você tem?"
        texto="Marque o que você tem, e o editor monta o caminho do vídeo. Os arquivos são copiados para uma pasta do seu computador — não vão para a internet." />
      <div className="linha-de-opcoes materiais" role="group" aria-label="o que você tem" data-tour="materiais">
        {MATERIAIS.map(([m, nome, dica]) => (
          <button key={m} type="button" className="pilula" aria-pressed={p.materiais.has(m)} title={dica}
            onClick={() => p.aoAlternarMaterial(m)}>{nome}</button>
        ))}
      </div>
      <ol className="trilha" aria-label="a trilha do vídeo" data-tour="trilha">
        {t.etapas.map((e) => (
          <li key={e.id} className="etapa" aria-label={e.titulo}>
            <strong>{e.titulo}</strong>
            <small>{e.id === 'por-cima' && p.montagem.porCima !== t.porCima ? TEXTO_DO_POR_CIMA[p.montagem.porCima]
              : e.texto}</small>
            {campos[e.id]}
          </li>
        ))}
      </ol>
      {t.bloqueio ? <div className="aviso" role="status">{t.bloqueio}</div> : null}
      {t.modo === 'montagem' ? <AjustarAsCamadas {...p} /> : null}
      <OndePostar {...p} />
    </section>
  );
};
