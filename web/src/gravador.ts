/**
 * O microfone da página: o formato que o navegador grava, sem os "melhoramentos" dele, a
 * barra de nível e gravar/parar. Usado pela leitura da Minha voz e pela amostra do estúdio
 * de voz.
 */
import {useCallback, useEffect, useRef, useState} from 'react';

/** O formato que o navegador grava: Opus em WebM (Chrome, Firefox) ou AAC em MP4 (Safari). */
export function formatoDeGravacao(): {mime: string; extensao: string} {
  const opcoes: [string, string][] = [['audio/webm;codecs=opus', '.webm'], ['audio/webm', '.webm'],
    ['audio/mp4', '.m4a'], ['audio/ogg;codecs=opus', '.ogg']];
  for (const [mime, extensao] of opcoes) {
    if (typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported(mime)) return {mime, extensao};
  }
  return {mime: '', extensao: '.webm'};
}

export type Gravador = {
  gravando: boolean;
  /** Abre o microfone (na primeira vez) e começa; ``aoTerminar`` recebe o áudio quando parar.
   *  Rejeita quando o microfone não pode ser usado. */
  gravar: (aoTerminar: (audio: Blob, extensao: string) => void) => Promise<void>;
  parar: () => void;
  /** Solta o microfone (a luz do navegador apaga). */
  soltar: () => void;
  /** A barra de nível: a largura acompanha o volume do microfone. */
  nivel: React.RefObject<HTMLDivElement | null>;
};

export function useGravador(): Gravador {
  const [gravando, setGravando] = useState(false);
  const microfone = useRef<MediaStream | null>(null);
  const gravador = useRef<MediaRecorder | null>(null);
  const medidor = useRef<{ctx: AudioContext; quadro: number} | null>(null);
  const nivel = useRef<HTMLDivElement>(null);

  const soltar = useCallback(() => {
    if (medidor.current) {
      cancelAnimationFrame(medidor.current.quadro);
      void medidor.current.ctx.close();
      medidor.current = null;
    }
    microfone.current?.getTracks().forEach((t) => t.stop());
    microfone.current = null;
  }, []);
  useEffect(() => soltar, [soltar]);

  const abrir = async (): Promise<MediaStream> => {
    if (microfone.current) return microfone.current;
    // Sem os "melhoramentos" do navegador: o redutor de ruído deixa a voz metálica, e o
    // modelo (ou o efeito) copiaria o metal.
    const s = await navigator.mediaDevices.getUserMedia({
      audio: {echoCancellation: false, noiseSuppression: false, autoGainControl: false, channelCount: 1},
    });
    microfone.current = s;
    const ctx = new AudioContext();
    const analisador = ctx.createAnalyser();
    analisador.fftSize = 1024;
    ctx.createMediaStreamSource(s).connect(analisador);
    const amostras = new Float32Array(analisador.fftSize);
    const passo = () => {
      analisador.getFloatTimeDomainData(amostras);
      let soma = 0;
      for (const v of amostras) soma += v * v;
      const db = 20 * Math.log10(Math.sqrt(soma / amostras.length) + 1e-9);
      if (nivel.current) nivel.current.style.width = `${Math.min(100, Math.max(0, (db + 60) * 1.8))}%`;
      if (medidor.current) medidor.current.quadro = requestAnimationFrame(passo);
    };
    medidor.current = {ctx, quadro: requestAnimationFrame(passo)};
    return s;
  };

  const gravar = async (aoTerminar: (audio: Blob, extensao: string) => void) => {
    const s = await abrir();
    const {mime, extensao} = formatoDeGravacao();
    const r = new MediaRecorder(s, mime ? {mimeType: mime} : undefined);
    const partes: Blob[] = [];
    r.ondataavailable = (e) => {
      if (e.data.size) partes.push(e.data);
    };
    r.onstop = () => aoTerminar(new Blob(partes, {type: r.mimeType || mime}), extensao);
    r.start();
    gravador.current = r;
    setGravando(true);
  };

  const parar = () => {
    gravador.current?.stop();
    gravador.current = null;
    setGravando(false);
  };

  return {gravando, gravar, parar, soltar, nivel};
}
