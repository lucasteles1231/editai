/**
 * O criador de avatar, no cartão "Avatar" de "Antes de começar".
 *
 * 1. A foto (opcional) e "Montar pela foto com o Gemini": ele escolhe uma parte de cada
 *    categoria e as cores, só entre as do catálogo. A foto não fica guardada.
 * 2. As partes e as cores, à mão (com ou sem o Gemini), com a prévia falando.
 * 3. "Aprovar e criar os quadros": o navegador desenha os 36 quadros (12 poses × 3 bocas) e
 *    manda ao servidor. Dali em diante o avatar vai na montagem, na thumbnail e no pacote.
 */
import React, {useCallback, useEffect, useRef, useState} from 'react';
import {api} from '../api';
import {abrirConfiguracao} from '../configurar';
import type {AvatarSalvo, EstadoIa} from '../tipos';
import {CATEGORIAS, CORES, ESCOLHIDAS, type EspacoDeCor, escolhasPadrao, espacosUsados, nomeDaOpcao} from './catalogo';
import {BOCAS, type Boca, type Escolhas, POSES, type Pose, desenharQuadro, desenharRecorte, nomeDoQuadro} from './desenhar';

type Props = {
  ia: EstadoIa | null;
  avatares: AvatarSalvo[] | null;
  aoMudarAvatares: (a: AvatarSalvo[]) => void;
};

/** O que está sendo montado sobrevive a fechar o painel (para colar a chave do Gemini e
 *  voltar, por exemplo). */
let rascunho: {escolhas: Escolhas; nome: string} | null = null;

/** O recorte das miniaturas, em pixels da grade: a cabeça, ou o tronco na roupa. */
const RECORTE_DA_CABECA: [number, number, number, number] = [25, 0, 100, 96];
const RECORTE_DO_TRONCO: [number, number, number, number] = [10, 44, 130, 86];
/** As poses pequenas da prévia. */
const POSES_DA_PREVIA: Pose[] = ['explicando', 'apontando_lado', 'joinha', 'pensando'];
/** A boca da prévia falando: uma sílaba forte, uma fraca e a pausa (a 10 quadros por segundo). */
const FALA_DA_PREVIA: Boca[] = ['meia', 'aberta', 'aberta', 'meia', 'fechada', 'meia', 'meia', 'fechada',
  'meia', 'aberta', 'meia', 'fechada', 'fechada', 'fechada'];

const comParte = (e: Escolhas, categoria: string, id: string): Escolhas => ({...e, [categoria]: id});
const comCor = (e: Escolhas, espaco: EspacoDeCor, cor: string): Escolhas => ({...e, cores: {...e.cores, [espaco]: cor}});
const valor = (e: Escolhas, categoria: string) => (e as unknown as Record<string, string>)[categoria];

/** Uma imagem desenhada pelo desenhista do avatar (um quadro inteiro ou um recorte). */
const Desenho: React.FC<{
  e: Escolhas; pose?: Pose; boca?: Boca; recorte?: [number, number, number, number]; lado: number; rotulo?: string;
}> = ({e, pose = 'neutro', boca = 'fechada', recorte, lado, rotulo}) => {
  const [url, setUrl] = useState('');
  const chave = JSON.stringify([e, pose, boca, recorte]);
  useEffect(() => {
    let vivo = true;
    const feito = recorte ? desenharRecorte(e, pose, boca, recorte, 2) : desenharQuadro(e, pose, boca, 300);
    feito.then((c) => vivo && setUrl(c.toDataURL())).catch(() => undefined);
    return () => {
      vivo = false;
    };
    // a chave resume as dependências: o objeto das escolhas é novo a cada render
  }, [chave]);
  return url ? <img src={url} width={lado} height={lado} alt={rotulo ?? ''} className="pixel" />
    : <span className="desenhando" style={{width: lado, height: lado}} aria-hidden="true" />;
};

/** A prévia grande, falando (a boca de um projeto anterior: meia, aberta, meia, fechada…). */
const Falando: React.FC<{e: Escolhas}> = ({e}) => {
  const [quadros, setQuadros] = useState<Record<string, string>>({});
  const [falando, setFalando] = useState(() => !window.matchMedia?.('(prefers-reduced-motion: reduce)').matches);
  const [passo, setPasso] = useState(0);
  const chave = JSON.stringify(e);
  useEffect(() => {
    let vivo = true;
    Promise.all(BOCAS.map((b) => desenharQuadro(e, 'neutro', b, 450).then((c) => [b, c.toDataURL()] as const)))
      .then((r) => vivo && setQuadros(Object.fromEntries(r))).catch(() => undefined);
    return () => {
      vivo = false;
    };
  }, [chave]);
  useEffect(() => {
    if (!falando) return undefined;
    const id = window.setInterval(() => setPasso((n) => (n + 1) % FALA_DA_PREVIA.length), 100);
    return () => window.clearInterval(id);
  }, [falando]);
  const boca = falando ? FALA_DA_PREVIA[passo] : 'fechada';
  return (
    <div className="avatar-falando">
      {quadros[boca] ? <img src={quadros[boca]} width={300} height={300} alt="a prévia do avatar" className="pixel" />
        : <span className="desenhando" style={{width: 300, height: 300}} aria-hidden="true" />}
      <button type="button" className="botao pequeno" aria-pressed={falando} onClick={() => setFalando((f) => !f)}>
        {falando ? 'Parar a fala' : 'Ver falando'}
      </button>
    </div>
  );
};

/** "Tirar uma foto": a câmera do computador, um quadro só. */
const Camera: React.FC<{aoTirar: (foto: Blob) => void; aoFechar: () => void}> = ({aoTirar, aoFechar}) => {
  const video = useRef<HTMLVideoElement>(null);
  const [erro, setErro] = useState('');
  useEffect(() => {
    let fluxo: MediaStream | null = null;
    navigator.mediaDevices?.getUserMedia({video: {width: 1280, height: 720}})
      .then((f) => {
        fluxo = f;
        if (video.current) video.current.srcObject = f;
      })
      .catch(() => setErro('Não consegui abrir a câmera. Confira a permissão do navegador, ou escolha uma foto.'));
    return () => fluxo?.getTracks().forEach((t) => t.stop());
  }, []);
  const tirar = () => {
    const v = video.current;
    if (!v || !v.videoWidth) return;
    const c = document.createElement('canvas');
    c.width = v.videoWidth;
    c.height = v.videoHeight;
    c.getContext('2d')!.drawImage(v, 0, 0);
    c.toBlob((b) => b && aoTirar(b), 'image/jpeg', 0.9);
  };
  return (
    <div className="camera-do-avatar">
      {erro ? <div className="aviso erro">{erro}</div> : <video ref={video} autoPlay playsInline muted />}
      <div className="linha-de-opcoes">
        <button type="button" className="botao" disabled={Boolean(erro)} onClick={tirar}>Tirar a foto</button>
        <button type="button" className="botao pequeno" onClick={aoFechar}>Cancelar</button>
      </div>
    </div>
  );
};

export const Criador: React.FC<Props> = ({ia, avatares, aoMudarAvatares}) => {
  const [e, setE] = useState<Escolhas>(() => rascunho?.escolhas ?? escolhasPadrao());
  const [nome, setNome] = useState(() => rascunho?.nome ?? '');
  const [foto, setFoto] = useState<Blob | null>(null);
  const [fotoUrl, setFotoUrl] = useState('');
  const [camera, setCamera] = useState(false);
  const [lendo, setLendo] = useState(false);
  const [visto, setVisto] = useState('');
  const [criando, setCriando] = useState<string | null>(null);
  const [erro, setErro] = useState('');
  const [pronto, setPronto] = useState('');
  rascunho = {escolhas: e, nome};

  useEffect(() => {
    if (!foto) return undefined;
    const url = URL.createObjectURL(foto);
    setFotoUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [foto]);

  const escolherFoto = (f: Blob | null) => {
    setFoto(f);
    setCamera(false);
    setVisto('');
    setErro('');
  };

  const montarPelaFoto = async () => {
    if (!foto) return;
    setLendo(true);
    setErro('');
    try {
      const r = await api.partesPelaFoto(foto);
      setE(r.escolhas);
      setVisto(r.descricao);
    } catch (x) {
      setErro((x as Error).message);
    } finally {
      setLendo(false);
    }
  };

  const criar = async () => {
    setErro('');
    setPronto('');
    const quadros: {nome: string; png: Blob}[] = [];
    try {
      for (const pose of POSES) {
        for (const boca of BOCAS) {
          setCriando(`Desenhando o quadro ${quadros.length + 1} de ${POSES.length * BOCAS.length}…`);
          const c = await desenharQuadro(e, pose, boca);
          const png = await new Promise<Blob>((ok, falha) =>
            c.toBlob((b) => (b ? ok(b) : falha(new Error('Não consegui gerar o PNG do quadro.'))), 'image/png'));
          quadros.push({nome: nomeDoQuadro(pose, boca), png});
        }
      }
      setCriando('Guardando os quadros…');
      const r = await api.salvarAvatar(nome, e, quadros);
      aoMudarAvatares(r.avatares);
      setPronto(`Pronto: o avatar ${r.avatar.nome} já pode ir na montagem ("Por cima → Meu avatar"), `
        + 'na thumbnail e no pacote para baixar.');
    } catch (x) {
      setErro((x as Error).message);
    } finally {
      setCriando(null);
    }
  };

  const ajustar = useCallback((a: AvatarSalvo) => {
    setE(a.escolhas);
    setNome(a.nome);
    setPronto('');
    setVisto('');
  }, []);

  const apagar = async (a: AvatarSalvo) => {
    if (!window.confirm(`Apagar o avatar ${a.nome}? Os quadros dele somem deste computador.`)) return;
    try {
      aoMudarAvatares((await api.apagarAvatar(a.apelido)).avatares);
    } catch (x) {
      setErro((x as Error).message);
    }
  };

  const espacos = espacosUsados(e);
  return (
    <div className="criador-de-avatar">
      {avatares?.length ? (
        <section className="avatares-salvos" aria-label="os seus avatares">
          {avatares.map((a) => (
            <article key={a.apelido} className="avatar-salvo" aria-label={`avatar ${a.nome}`}>
              <img src={api.quadroDoAvatarUrl(a.apelido, 'neutro_fechada.png', a.criado)} alt="" width={72} height={72}
                className="pixel" />
              <div>
                <strong>{a.nome}</strong>
                <small>criado em {a.criado.slice(0, 16)}</small>
                <div className="linha-de-opcoes">
                  <button type="button" className="botao pequeno" onClick={() => ajustar(a)}>Ajustar</button>
                  <a className="botao pequeno" href={api.pacoteDoAvatarUrl(a.apelido)} download>Baixar o pacote</a>
                  <button type="button" className="botao pequeno" onClick={() => void apagar(a)}>Apagar</button>
                </div>
              </div>
            </article>
          ))}
        </section>
      ) : null}

      <div className="mesa-do-avatar">
        <div className="previa-do-avatar">
          <Falando e={e} />
          <div className="poses-da-previa" aria-label="algumas das 12 poses">
            {POSES_DA_PREVIA.map((p) => <Desenho key={p} e={e} pose={p} lado={96} rotulo={`pose ${p}`} />)}
          </div>
          <small>São 12 poses, cada uma com 3 bocas. No vídeo, a pose muda a cada frase e a boca abre nas sílabas
            da voz.</small>
        </div>

        <div className="partes-do-avatar">
          <section className="campo foto-do-avatar" aria-label="pela foto">
            <span>Pela foto (opcional)</span>
            <div className="linha-de-opcoes">
              <label className="botao pequeno">
                Escolher uma foto
                <input type="file" accept="image/*" hidden
                  onChange={(ev) => escolherFoto(ev.target.files?.[0] ?? null)} />
              </label>
              <button type="button" className="botao pequeno" onClick={() => setCamera(true)}>Tirar uma foto</button>
            </div>
            {camera ? <Camera aoTirar={escolherFoto} aoFechar={() => setCamera(false)} /> : null}
            {fotoUrl ? (
              <div className="foto-escolhida">
                <img src={fotoUrl} alt="a foto escolhida" />
                {ia?.configurada ? (
                  <button type="button" className="botao" disabled={lendo} onClick={() => void montarPelaFoto()}>
                    {lendo ? 'O Gemini está olhando a foto…' : 'Montar pela foto com o Gemini (grátis)'}
                  </button>
                ) : (
                  <button type="button" className="botao pequeno" onClick={() => abrirConfiguracao('gemini')}>
                    Colar a chave do Gemini para montar pela foto
                  </button>
                )}
              </div>
            ) : null}
            <small>Na cota grátis, o Google pode usar o que você envia para melhorar os produtos dele. A foto não
              fica guardada no Editai: só as partes e as cores que o Gemini escolheu.</small>
            {visto ? <div className="aviso">O Gemini viu: {visto}. Ajuste o que quiser abaixo.</div> : null}
          </section>

          {ESCOLHIDAS.map((categoria) => {
            const c = CATEGORIAS[categoria];
            const ids = ['nenhum', ...c.opcoes.map((o) => o.id)];
            const recorte = categoria === 'roupa' ? RECORTE_DO_TRONCO : RECORTE_DA_CABECA;
            return (
              <section key={categoria} className="campo">
                <span>{c.rotulo}: {nomeDaOpcao(categoria, valor(e, categoria))}</span>
                <div className="opcoes-do-avatar" role="group" aria-label={c.rotulo}>
                  {ids.map((id) => (
                    <button key={id} type="button" className="opcao-do-avatar" aria-pressed={valor(e, categoria) === id}
                      title={nomeDaOpcao(categoria, id)} aria-label={nomeDaOpcao(categoria, id)}
                      onClick={() => setE(comParte(e, categoria, id))}>
                      <Desenho e={comParte(e, categoria, id)} recorte={recorte} lado={64} />
                      <small>{nomeDaOpcao(categoria, id)}</small>
                    </button>
                  ))}
                </div>
              </section>
            );
          })}

          <section className="campo" aria-label="as cores">
            <span>As cores</span>
            {espacos.map((espaco) => {
              const info = CORES[espaco];
              const atual = e.cores[espaco];
              return (
                <div key={espaco} className="cor-do-avatar" role="group" aria-label={`cor: ${info.rotulo}`}>
                  <small>{info.rotulo}</small>
                  {info.vazia ? (
                    <button type="button" className="amostra vazia" aria-pressed={!atual} title={info.vazia}
                      aria-label={info.vazia} onClick={() => setE(comCor(e, espaco, ''))}>=</button>
                  ) : null}
                  {Object.entries(info.sugestoes).map(([cor, rotulo]) => (
                    <button key={cor} type="button" className="amostra" style={{background: cor}} title={rotulo}
                      aria-label={`${info.rotulo} ${rotulo}`} aria-pressed={atual === cor}
                      onClick={() => setE(comCor(e, espaco, cor))} />
                  ))}
                  <input type="color" aria-label={`outra cor: ${info.rotulo}`}
                    value={atual || e.cores.cabelo || '#000000'}
                    onChange={(ev) => setE(comCor(e, espaco, ev.target.value))} />
                </div>
              );
            })}
          </section>

          <section className="campo aprovar-avatar" aria-label="aprovar">
            <label className="campo">
              <span>Nome do avatar</span>
              <input type="text" value={nome} maxLength={40} placeholder="o seu nome, ou o do personagem"
                onChange={(ev) => setNome(ev.target.value)} />
            </label>
            <button type="button" className="botao rosa" disabled={Boolean(criando) || !nome.trim()}
              onClick={() => void criar()}>
              Aprovar e criar os quadros
            </button>
            {criando ? <small className="andamento" aria-live="polite">{criando}</small> : null}
            {pronto ? <div className="aviso ok" role="status">{pronto}</div> : null}
            {erro ? <div className="aviso erro">{erro}</div> : null}
          </section>
        </div>
      </div>
    </div>
  );
};
