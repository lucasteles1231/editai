/**
 * O tocador A/B do estúdio de voz: dois AudioBuffer (A, sem efeito; B, com efeito) no mesmo
 * AudioContext. Trocar de um para o outro, ou receber uma versão nova do B, continua do
 * mesmo instante: é o que deixa ouvir a diferença. E os picos da forma de onda, para o
 * canvas.
 */
export type Lado = 'a' | 'b';

export class TocadorAB {
  private ctx: AudioContext | null = null;
  private buffers: Record<Lado, AudioBuffer | null> = {a: null, b: null};
  private fonte: AudioBufferSourceNode | null = null;
  /** O ``currentTime`` do contexto quando a fonte começou, e de que ponto do áudio. */
  private inicio = 0;
  private deslocamento = 0;
  lado: Lado = 'b';
  laco = true;
  tocando = false;
  /** Chamado a cada mudança de estado (tocar, pausar, trocar, acabar). */
  aoMudar: () => void = () => undefined;

  private contexto(): AudioContext {
    if (!this.ctx) this.ctx = new AudioContext();
    return this.ctx;
  }

  buffer(lado: Lado): AudioBuffer | null {
    return this.buffers[lado];
  }

  /** Decodifica um WAV e guarda no lado pedido; se é o lado tocando, troca sem parar. */
  async carregar(lado: Lado, dados: ArrayBuffer): Promise<AudioBuffer> {
    const buf = await this.contexto().decodeAudioData(dados);
    const onde = this.posicao();
    this.buffers[lado] = buf;
    if (this.tocando && lado === this.lado) this.comecar(onde);
    this.aoMudar();
    return buf;
  }

  /** Onde está, em segundos, no áudio do lado escolhido. */
  posicao(): number {
    const buf = this.buffers[this.lado];
    if (!buf) return 0;
    if (!this.tocando || !this.ctx) return Math.min(this.deslocamento, buf.duration);
    const t = this.deslocamento + (this.ctx.currentTime - this.inicio);
    return this.laco ? t % buf.duration : Math.min(t, buf.duration);
  }

  duracao(): number {
    return this.buffers[this.lado]?.duration ?? 0;
  }

  private soltarFonte(): void {
    const f = this.fonte;
    this.fonte = null;
    if (f) {
      f.onended = null;
      try {
        f.stop();
      } catch {
        // já parou
      }
      f.disconnect();
    }
  }

  private comecar(de: number): void {
    this.soltarFonte();
    const buf = this.buffers[this.lado];
    if (!buf) return;
    const ctx = this.contexto();
    const f = ctx.createBufferSource();
    f.buffer = buf;
    f.loop = this.laco;
    f.connect(ctx.destination);
    f.onended = () => {
      if (this.fonte !== f) return;
      this.fonte = null;
      this.tocando = false;
      this.deslocamento = 0;
      this.aoMudar();
    };
    const ponto = de >= buf.duration - 0.02 ? 0 : de;
    f.start(0, ponto);
    this.fonte = f;
    this.inicio = ctx.currentTime;
    this.deslocamento = ponto;
    this.tocando = true;
  }

  tocar(): void {
    void this.contexto().resume();
    this.comecar(this.posicao());
    this.aoMudar();
  }

  pausar(): void {
    this.deslocamento = this.posicao();
    this.soltarFonte();
    this.tocando = false;
    this.aoMudar();
  }

  /** Pula para um ponto (o clique na forma de onda). */
  ir(segundos: number): void {
    const fim = this.duracao();
    const ponto = Math.max(0, Math.min(segundos, fim));
    if (this.tocando) this.comecar(ponto);
    else this.deslocamento = ponto;
    this.aoMudar();
  }

  escolher(lado: Lado): void {
    const onde = this.posicao();
    this.lado = lado;
    if (this.tocando) this.comecar(onde);
    else this.deslocamento = onde;
    this.aoMudar();
  }

  mudarLaco(laco: boolean): void {
    const onde = this.posicao();
    this.laco = laco;
    if (this.tocando) this.comecar(onde);
    this.aoMudar();
  }

  /** Volta ao começo e esquece os dois áudios (outra amostra vem aí). */
  esvaziar(): void {
    this.soltarFonte();
    this.tocando = false;
    this.deslocamento = 0;
    this.buffers = {a: null, b: null};
    this.aoMudar();
  }

  fechar(): void {
    this.esvaziar();
    void this.ctx?.close();
    this.ctx = null;
  }
}

/** O maior valor absoluto (dos dois canais) em cada uma das ``colunas`` do áudio. */
export function picos(buf: AudioBuffer, colunas: number): Float32Array {
  const saida = new Float32Array(colunas);
  const canais = Array.from({length: buf.numberOfChannels}, (_, c) => buf.getChannelData(c));
  const passo = buf.length / colunas;
  for (let k = 0; k < colunas; k++) {
    const ini = Math.floor(k * passo);
    const fim = Math.min(buf.length, Math.floor((k + 1) * passo));
    let maior = 0;
    for (const dados of canais) {
      for (let i = ini; i < fim; i++) {
        const v = Math.abs(dados[i]);
        if (v > maior) maior = v;
      }
    }
    saida[k] = maior;
  }
  return saida;
}
