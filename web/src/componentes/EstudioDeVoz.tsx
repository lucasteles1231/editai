/**
 * O estúdio de voz: uma tela só para montar um efeito de ouvido e guardar como seu.
 *
 * - **A amostra:** a fala do vídeo, uma gravação feita aqui (o microfone) ou um arquivo; os
 *   dois últimos sobem como um áudio qualquer (``/api/audios``).
 * - **O tocador:** o A (sem efeito) e o B (com efeito) saem do mesmo caminho da edição
 *   (``/api/efeitos/ouvir``, com o tratamento do passo 2); trocar de um para o outro continua
 *   do mesmo instante, e o B é pedido de novo 400 ms depois de cada mudança nos controles.
 * - **Os seus efeitos:** salvar, editar (e renomear), duplicar, apagar, exportar e importar.
 *
 * É um ``<dialog>`` nativo: o foco fica nele, o Esc fecha, e o resto da página espera.
 */
import React, {useCallback, useEffect, useRef, useState} from 'react';
import {api} from '../api';
import {escreverEfeito, lerEfeito} from '../efeitos';
import {useGravador} from '../gravador';
import {apelido} from '../presets';
import {type Lado, TocadorAB, picos} from '../tocador';
import type {EfeitoDeVoz, EfeitosDaVoz, Voz} from '../tipos';
import {ControlesDaVoz} from './ControlesDaVoz';

/** Quanto esperar, depois de mexer num controle, para pedir o B de novo. */
const ESPERA_MS = 400;
const NOME_DO_TRATAMENTO: Record<Voz, string> = {original: 'Original', limpa: 'Limpa', estudio: 'Estúdio'};
const mensagem = (e: unknown) => (e as Error).message;

type Amostra = {tipo: 'video' | 'gravacao' | 'arquivo'; fonte: string | null; nome: string};
type Carga = 'vazio' | 'carregando' | 'pronto';

type Props = {
  /** O efeito com que o estúdio abre e, se for um seu aberto pelo ✎, ele mesmo. */
  efeito: string;
  editando: EfeitoDeVoz | null;
  catalogo: EfeitosDaVoz;
  aoMudarCatalogo: (c: EfeitosDaVoz) => void;
  /** O tratamento do passo 2: o A e o B passam por ele, como na edição. */
  tratamento: Voz;
  /** A fala do vídeo ("audio:ID" ou "video:ID"), quando já há uma. */
  fonteDoVideo: string | null;
  aoUsar: (efeito: string) => void;
  aoFechar: () => void;
};

const cacheDePicos = new WeakMap<AudioBuffer, Float32Array>();

export const EstudioDeVoz: React.FC<Props> = (p) => {
  const dialogo = useRef<HTMLDialogElement>(null);
  const tela = useRef<HTMLCanvasElement>(null);
  const arquivo = useRef<HTMLInputElement>(null);
  const tocadorRef = useRef<TocadorAB | null>(null);
  if (!tocadorRef.current) tocadorRef.current = new TocadorAB();
  const tocador = tocadorRef.current;
  const [, setTique] = useState(0);
  const [efeito, setEfeito] = useState(p.efeito);
  const [editando, setEditando] = useState<EfeitoDeVoz | null>(p.editando);
  const [nome, setNome] = useState(p.editando?.titulo ?? '');
  const [frase, setFrase] = useState(p.editando?.frase ?? '');
  const [amostra, setAmostra] = useState<Amostra>(p.fonteDoVideo
    ? {tipo: 'video', fonte: p.fonteDoVideo, nome: 'a fala do vídeo'} : {tipo: 'gravacao', fonte: null, nome: ''});
  const [segundos, setSegundos] = useState(8);
  const [cargaA, setCargaA] = useState<Carga>('vazio');
  const [cargaB, setCargaB] = useState<Carga>('vazio');
  const [enviando, setEnviando] = useState('');
  const [conflito, setConflito] = useState(false);
  const [erro, setErro] = useState('');
  const [aviso, setAviso] = useState('');
  const gravador = useGravador();
  const vezes = useRef(0);
  const ajustes = lerEfeito(efeito);
  const meus = p.catalogo.efeitos.filter((e) => e.meu);

  // abre como janela modal; ao desmontar, o som e o microfone param
  useEffect(() => {
    const d = dialogo.current;
    if (d && !d.open) d.showModal();
    tocador.aoMudar = () => setTique((n) => n + 1);
    return () => {
      tocador.fechar();
      gravador.soltar();
    };
  }, []);

  const baixar = useCallback(async (fonte: string, comEfeito: string): Promise<ArrayBuffer> => {
    vezes.current += 1;
    const r = await fetch(api.ouvirEfeitoUrl(fonte, comEfeito, p.tratamento, vezes.current, segundos));
    if (!r.ok) {
      let detalhe = '';
      try {
        detalhe = (await r.json()).detail;
      } catch {
        // sem corpo em JSON
      }
      throw new Error(detalhe || `A amostra não veio (${r.status}).`);
    }
    return r.arrayBuffer();
  }, [p.tratamento, segundos]);

  // o A: a amostra sem efeito, a cada amostra (ou duração, ou tratamento) nova
  useEffect(() => {
    tocador.esvaziar();
    setCargaA('vazio');
    setCargaB('vazio');
    const fonte = amostra.fonte;
    if (!fonte) return undefined;
    let vale = true;
    setCargaA('carregando');
    baixar(fonte, '')
      .then(async (dados) => {
        if (!vale) return;
        await tocador.carregar('a', dados);
        setCargaA('pronto');
      })
      .catch((e) => {
        if (!vale) return;
        setErro(`O som da amostra não abriu: ${mensagem(e)}`);
        setCargaA('vazio');
      });
    return () => {
      vale = false;
    };
  }, [amostra.fonte, baixar, tocador]);

  // o B: com o efeito, 400 ms depois da última mudança
  useEffect(() => {
    const fonte = amostra.fonte;
    if (!fonte) return undefined;
    let vale = true;
    setCargaB('carregando');
    const espera = setTimeout(() => {
      baixar(fonte, efeito)
        .then(async (dados) => {
          if (!vale) return;
          await tocador.carregar('b', dados);
          setCargaB('pronto');
        })
        .catch((e) => {
          if (!vale) return;
          setErro(`O som com o efeito não abriu: ${mensagem(e)}`);
          setCargaB('vazio');
        });
    }, ESPERA_MS);
    return () => {
      vale = false;
      clearTimeout(espera);
    };
  }, [amostra.fonte, efeito, baixar, tocador]);

  // a forma de onda do lado escolhido, com a agulha andando enquanto toca
  const desenhar = useCallback(() => {
    const c = tela.current;
    const g = c?.getContext('2d');
    if (!c || !g) return;
    g.clearRect(0, 0, c.width, c.height);
    const buf = tocador.buffer(tocador.lado) ?? tocador.buffer('a');
    if (!buf) return;
    let ps = cacheDePicos.get(buf);
    if (!ps || ps.length !== c.width) {
      ps = picos(buf, c.width);
      cacheDePicos.set(buf, ps);
    }
    const estilo = getComputedStyle(c);
    const tinta = estilo.getPropertyValue('--tinta').trim() || '#1a1a1a';
    g.fillStyle = tocador.lado === 'b' ? estilo.getPropertyValue('--rosa').trim() || '#ff3d7f' : tinta;
    const meio = c.height / 2;
    for (let k = 0; k < ps.length; k++) {
      const a = Math.min(1, ps[k]) * meio * 0.95;
      g.fillRect(k, meio - a, 1, Math.max(1, 2 * a));
    }
    g.fillStyle = tinta;
    g.fillRect(Math.round((tocador.posicao() / buf.duration) * c.width), 0, 2, c.height);
  }, [tocador]);

  useEffect(() => {
    desenhar();
    if (!tocador.tocando) return undefined;
    let quadro = 0;
    const passo = () => {
      desenhar();
      quadro = requestAnimationFrame(passo);
    };
    quadro = requestAnimationFrame(passo);
    return () => cancelAnimationFrame(quadro);
  });

  const fechar = () => dialogo.current?.close();

  const enviar = async (a: File, tipo: Amostra['tipo'], rotulo: string) => {
    setEnviando('Enviando a amostra…');
    setErro('');
    try {
      const info = await api.enviarAudio(a, () => undefined);
      setAmostra({tipo, fonte: `audio:${info.id}`, nome: rotulo});
    } catch (e) {
      setErro(mensagem(e));
    } finally {
      setEnviando('');
    }
  };

  const gravar = async () => {
    setErro('');
    try {
      await gravador.gravar((audio, extensao) =>
        void enviar(new File([audio], `amostra${extensao}`, {type: audio.type}), 'gravacao', 'a sua gravação'));
    } catch (e) {
      setErro(`Não deu para usar o microfone (${mensagem(e)}). Permita o microfone para esta página, no ícone da `
        + 'barra de endereço, ou envie um arquivo.');
    }
  };

  const abrirParaEditar = (e: EfeitoDeVoz) => {
    setEditando(e);
    setNome(e.titulo);
    setFrase(e.frase);
    setEfeito(e.efeito);
    setConflito(false);
    setErro('');
    setAviso('');
  };

  const duplicar = (e: EfeitoDeVoz) => {
    setEditando(null);
    setNome(`${e.titulo} (cópia)`.slice(0, 40));
    setFrase(e.frase);
    setEfeito(e.efeito);
    setConflito(false);
    setAviso(`Uma cópia de “${e.titulo}”: mude o que quiser e salve.`);
  };

  const apagar = async (e: EfeitoDeVoz) => {
    if (!window.confirm(`Apagar o efeito “${e.titulo}”?`)) return;
    setErro('');
    try {
      p.aoMudarCatalogo((await api.apagarEfeito(e.nome)).efeitos_da_voz);
      if (editando?.nome === e.nome) setEditando(null);
    } catch (x) {
      setErro(mensagem(x));
    }
  };

  const importar = async (a: File) => {
    setErro('');
    try {
      const r = await api.importarEfeitos(a);
      p.aoMudarCatalogo(r.efeitos_da_voz);
      const partes = [r.entraram.length ? `Entraram: ${r.entraram.join(', ')}.` : 'Nenhum efeito entrou.'];
      if (r.recusados.length) partes.push(`Ficaram de fora: ${r.recusados.join('; ')}.`);
      setAviso(partes.join(' '));
    } catch (x) {
      setErro(mensagem(x));
    }
  };

  /** Salva o que está na tela: edita o aberto pelo ✎ (o que também renomeia), ou cria um
   *  novo. O que a página já sabe ela diz na hora, sem pedir ao servidor. */
  const salvar = async (substituir: boolean, comoNovo = false) => {
    setErro('');
    setAviso('');
    const titulo = nome.trim();
    const n = apelido(titulo);
    if (!efeito) {
      setErro('Esse efeito não muda nada: mexa em pelo menos um controle.');
      return;
    }
    if (p.catalogo.efeitos.some((e) => !e.meu && (e.nome === n || apelido(e.titulo) === n))) {
      setErro(`“${titulo}” é o nome de um efeito pronto: escolha outro.`);
      return;
    }
    const alvo = comoNovo ? null : editando;
    const outro = meus.find((e) => e.nome === n && e.nome !== alvo?.nome);
    if (outro && alvo) {
      setErro(`Já existe um efeito seu chamado “${outro.titulo}”: escolha outro nome.`);
      return;
    }
    if (outro && !substituir) {
      setConflito(true);
      return;
    }
    try {
      const r = alvo ? await api.atualizarEfeito(alvo.nome, {titulo, frase, efeito})
        : await api.salvarEfeito({titulo, frase, efeito}, substituir);
      p.aoMudarCatalogo(r.efeitos_da_voz);
      setEditando(r.efeitos_da_voz.efeitos.find((e) => e.meu && e.nome === r.salvo) ?? null);
      setConflito(false);
      setAviso(`Salvo: “${titulo}”.`);
    } catch (x) {
      setErro(mensagem(x));
    }
  };

  const lado = tocador.lado;
  const podeTocar = Boolean(tocador.buffer(lado));
  const escolher = (l: Lado) => tocador.escolher(l);
  const pular = (ev: React.MouseEvent<HTMLCanvasElement>) => {
    const caixa = ev.currentTarget.getBoundingClientRect();
    tocador.ir(((ev.clientX - caixa.left) / caixa.width) * tocador.duracao());
  };

  return (
    <dialog ref={dialogo} className="estudio-de-voz" aria-labelledby="titulo-do-estudio" onClose={p.aoFechar}>
      <header className="topo-do-estudio">
        <h2 id="titulo-do-estudio">Estúdio de voz</h2>
        <button type="button" className="fechar-estudio" aria-label="fechar o estúdio" onClick={fechar}>×</button>
      </header>

      <section className="amostra-do-estudio" aria-label="a amostra">
        <div className="linha-de-opcoes" role="group" aria-label="de onde vem a amostra">
          <button type="button" className="pilula" aria-pressed={amostra.tipo === 'video'} disabled={!p.fonteDoVideo}
            title={p.fonteDoVideo ? '' : 'Envie a fala no passo 1 primeiro'}
            onClick={() => setAmostra({tipo: 'video', fonte: p.fonteDoVideo, nome: 'a fala do vídeo'})}>
            A fala do vídeo
          </button>
          <button type="button" className="pilula" aria-pressed={amostra.tipo === 'gravacao'}
            onClick={() => setAmostra({tipo: 'gravacao', fonte: null, nome: ''})}>Gravar agora</button>
          <button type="button" className="pilula" aria-pressed={amostra.tipo === 'arquivo'}
            onClick={() => arquivo.current?.click()}>Um arquivo</button>
          <input ref={arquivo} type="file" accept="audio/*,video/*,.m4a,.mp3,.wav" hidden
            aria-label="o arquivo da amostra" onChange={(e) => {
              const f = e.target.files?.[0];
              e.target.value = '';
              if (f) void enviar(f, 'arquivo', f.name);
            }} />
          <span className="separador" aria-hidden="true" />
          <div className="linha-de-opcoes" role="group" aria-label="duração da amostra">
            {[8, 15].map((s) => (
              <button key={s} type="button" className="pilula" aria-pressed={segundos === s}
                onClick={() => setSegundos(s)}>{s} s</button>
            ))}
          </div>
        </div>
        {amostra.tipo === 'gravacao' ? (
          <div className="linha-de-opcoes gravar">
            {gravador.gravando ? (
              <button type="button" className="botao pequeno rosa" onClick={gravador.parar}>Parar</button>
            ) : (
              <button type="button" className="botao pequeno" disabled={Boolean(enviando)} onClick={() => void gravar()}>
                {amostra.fonte ? 'Gravar de novo' : 'Gravar'}
              </button>
            )}
            <div className={`nivel${gravador.gravando ? ' gravando' : ''}`} aria-hidden="true"><div ref={gravador.nivel} /></div>
          </div>
        ) : null}
        <small aria-live="polite">
          {enviando || (amostra.fonte
            ? `Tocando ${amostra.nome}, com a voz ${NOME_DO_TRATAMENTO[p.tratamento]} do passo 2.`
            : 'Fale umas frases, aperte Parar, e a gravação vira a amostra. Ela fica só neste computador.')}
        </small>
      </section>

      <section className="tocador-do-estudio" aria-label="o tocador">
        <canvas ref={tela} width={900} height={110} role="img" aria-label="a forma de onda da amostra"
          onClick={pular} />
        <div className="linha-de-opcoes">
          <button type="button" className="botao pequeno" disabled={!podeTocar}
            onClick={() => (tocador.tocando ? tocador.pausar() : tocador.tocar())}>
            {tocador.tocando ? 'Pausar' : 'Tocar'}
          </button>
          <label className="marcar">
            <input type="checkbox" checked={tocador.laco} onChange={(e) => tocador.mudarLaco(e.target.checked)} />
            Em laço
          </label>
          <div className="linha-de-opcoes" role="group" aria-label="comparar">
            <button type="button" className="pilula" aria-pressed={lado === 'a'} onClick={() => escolher('a')}>
              A · sem efeito
            </button>
            <button type="button" className="pilula" aria-pressed={lado === 'b'} onClick={() => escolher('b')}>
              B · com efeito
            </button>
          </div>
          <small className="andamento" aria-live="polite">
            {cargaA === 'carregando' ? 'Abrindo a amostra…' : cargaB === 'carregando' ? 'Atualizando o B…'
              : cargaB === 'pronto' ? 'O B já é o efeito de agora.' : ''}
          </small>
        </div>
      </section>

      <section className="controles-do-estudio" aria-label="os controles">
        <div className="linha-de-opcoes">
          <label className="campo comecar-de">
            <span>Começar de</span>
            <select aria-label="começar de" value="" onChange={(e) => {
              const escolhido = p.catalogo.efeitos.find((x) => x.nome === e.target.value);
              if (escolhido) setEfeito(escolhido.efeito);
            }}>
              <option value="">Escolha um efeito…</option>
              <optgroup label="Prontos">
                {p.catalogo.efeitos.filter((x) => !x.meu).map((x) => <option key={x.nome} value={x.nome}>{x.titulo}</option>)}
              </optgroup>
              {meus.length ? (
                <optgroup label="Os seus">
                  {meus.map((x) => <option key={x.nome} value={x.nome}>{x.titulo}</option>)}
                </optgroup>
              ) : null}
            </select>
          </label>
          <button type="button" className="link" disabled={!efeito} onClick={() => setEfeito('')}>Zerar</button>
          <code className="texto-do-efeito" aria-label="o efeito como texto">{efeito || 'nenhum ajuste'}</code>
        </div>
        <ControlesDaVoz controles={p.catalogo.controles} ajustes={ajustes}
          ajustar={(chave, valor) => setEfeito(escreverEfeito({...ajustes, [chave]: valor}, p.catalogo.controles))} />
      </section>

      <div className="salvar-do-estudio">
        <form aria-label="salvar o efeito" onSubmit={(e) => {
          e.preventDefault();
          void salvar(false);
        }}>
          <label className="campo">
            <span>Nome do efeito</span>
            <input type="text" value={nome} maxLength={40} placeholder="Meu locutor"
              onChange={(e) => {
                setNome(e.target.value);
                setConflito(false);
              }} />
          </label>
          <label className="campo">
            <span>Frase (opcional)</span>
            <input type="text" value={frase} maxLength={120} placeholder="Como ele soa"
              onChange={(e) => setFrase(e.target.value)} />
          </label>
          {editando ? <small>Editando “{editando.titulo}”: salvar troca o que está guardado.</small> : null}
          {conflito ? <div className="aviso">Já existe um efeito seu com esse nome. Substituir pelo que está na tela?</div> : null}
          <div className="linha-de-opcoes">
            {conflito ? (
              <button type="button" className="botao pequeno usar" onClick={() => void salvar(true)}>Substituir</button>
            ) : (
              <button type="submit" className="botao pequeno usar" disabled={!nome.trim()}>Salvar</button>
            )}
            {editando ? (
              <button type="button" className="botao pequeno" disabled={!nome.trim()}
                onClick={() => void salvar(false, true)}>Salvar como novo</button>
            ) : null}
          </div>
        </form>

        <section className="meus-efeitos" aria-label="os seus efeitos">
          <strong>Os seus efeitos</strong>
          {meus.length ? (
            <ul>
              {meus.map((e) => (
                <li key={e.nome} aria-current={editando?.nome === e.nome ? 'true' : undefined}>
                  <span>
                    {e.titulo}
                    <code>{e.efeito}</code>
                  </span>
                  <button type="button" className="icone-do-estudio" aria-label={`editar o efeito ${e.titulo}`}
                    title="Editar" onClick={() => abrirParaEditar(e)}>✎</button>
                  <button type="button" className="icone-do-estudio" aria-label={`duplicar o efeito ${e.titulo}`}
                    title="Duplicar" onClick={() => duplicar(e)}>⧉</button>
                  <button type="button" className="icone-do-estudio" aria-label={`apagar o efeito ${e.titulo}`}
                    title="Apagar" onClick={() => void apagar(e)}>×</button>
                </li>
              ))}
            </ul>
          ) : <small>Nenhum ainda: monte um e salve. Eles ficam só neste computador.</small>}
          <div className="linha-de-opcoes">
            {meus.length ? (
              <a className="link" href={api.exportarEfeitosUrl()} download="meus-efeitos-de-voz.json">Exportar os seus</a>
            ) : null}
            <label className="link">
              Importar
              <input type="file" accept=".json,application/json" hidden aria-label="importar efeitos"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  e.target.value = '';
                  if (f) void importar(f);
                }} />
            </label>
          </div>
        </section>
      </div>

      {aviso ? <div className="aviso" role="status">{aviso}</div> : null}
      {erro ? <div className="aviso erro">{erro}</div> : null}

      <footer className="rodape-do-estudio linha-de-opcoes">
        <button type="button" className="botao usar" onClick={() => {
          p.aoUsar(efeito);
          fechar();
        }}>Usar no vídeo</button>
        <button type="button" className="botao pequeno" onClick={fechar}>Fechar sem usar</button>
      </footer>
    </dialog>
  );
};
