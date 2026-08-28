// SPDX-License-Identifier: MIT
// Energy-based voice activity detection. Replaces the ONNX/wasm Silero VAD
// (which never fired onSpeechStart reliably in this setup) with a self-
// contained RMS-threshold detector: PCM frames are buffered, and an utterance
// is flushed after a run of low-energy frames.

export function buildWavBuffer(samples: Float32Array): ArrayBuffer {
  const sampleRate = 16000;
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const writeStr = (offset: number, s: string) => {
    for (let i = 0; i < s.length; i++) view.setUint8(offset + i, s.charCodeAt(i));
  };
  writeStr(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  writeStr(8, "WAVE");
  writeStr(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeStr(36, "data");
  view.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) {
    const clamped = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(
      44 + i * 2,
      clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff,
      true
    );
  }
  return buffer;
}

export function encodeWavToBlob(samples: Float32Array): Blob {
  return new Blob([buildWavBuffer(samples)], { type: "audio/wav" });
}

/** RMS energy of a Float32Array in [-1, 1], normalized to [0, 1]. */
export function computeRmsEnergy(samples: Float32Array): number {
  if (samples.length === 0) return 0;
  let sum = 0;
  for (let i = 0; i < samples.length; i++) {
    sum += samples[i] * samples[i];
  }
  return Math.sqrt(sum / samples.length);
}

const SPEECH_ENERGY_THRESHOLD = 0.02;
const SILENCE_FLUSH_MS = 700;
const MIN_UTTERANCE_MS = 200;
const FRAME_SAMPLES = 4096;

interface EnergyVadCallbacks {
  onUtterance: (blob: Blob) => void;
  onSpeechStart?: () => void;
  onLevel?: (level: number) => void;
}

export class EnergyVad {
  private callbacks: EnergyVadCallbacks;
  private audioContext: AudioContext | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private processor: ScriptProcessorNode | null = null;
  private stream: MediaStream | null = null;
  private buffer: Float32Array[] = [];
  private bufferedMs = 0;
  private silenceMs = 0;
  private speechDetected = false;
  private _listening = false;
  private _userSpeaking = false;
  private sampleRate = 16000;
  private destroyed = false;
  private capturePaused = false;

  constructor(callbacks: EnergyVadCallbacks) {
    this.callbacks = callbacks;
  }

  get listening(): boolean {
    return this._listening;
  }

  get userSpeaking(): boolean {
    return this._userSpeaking;
  }

  ensureUnlocked(): void {
    const ctx = this.audioContext;
    if (!ctx) return;
    if (ctx.state === "suspended") {
      void ctx.resume();
    }
    const silent = ctx.createBuffer(1, 1, ctx.sampleRate);
    const source = ctx.createBufferSource();
    source.buffer = silent;
    source.connect(ctx.destination);
    source.start();
  }

  async start(): Promise<void> {
    this.destroy();
    this.destroyed = false;
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1 },
    });
    this.stream = stream;
    const ctx = new AudioContext();
    this.audioContext = ctx;
    if (ctx.state === "suspended") {
      await ctx.resume();
    }
    this.ensureUnlocked();
    this.sampleRate = ctx.sampleRate;
    this.source = ctx.createMediaStreamSource(stream);
    this.processor = ctx.createScriptProcessor(FRAME_SAMPLES, 1, 1);
    this.processor.onaudioprocess = (event) => {
      if (this.destroyed) return;
      const input = event.inputBuffer.getChannelData(0);
      this.pushFrame(input);
    };
    this.source.connect(this.processor);
    this.processor.connect(ctx.destination);
    this._listening = true;
  }

  private pushFrame(frame: Float32Array): void {
    if (this.capturePaused) return;
    // Copy: ScriptProcessor reuses the inputBuffer, so storing the reference
    // would leave every buffered frame pointing at the last-written data.
    this.buffer.push(new Float32Array(frame));
    const frameMs = (frame.length / this.sampleRate) * 1000;
    this.bufferedMs += frameMs;
    const energy = computeRmsEnergy(frame);
    this.callbacks.onLevel?.(energy);
    if (energy >= SPEECH_ENERGY_THRESHOLD) {
      if (!this.speechDetected) {
        this.speechDetected = true;
        this._userSpeaking = true;
        this.callbacks.onSpeechStart?.();
      }
      this.silenceMs = 0;
      return;
    }
    if (!this.speechDetected) return;
    this.silenceMs += frameMs;
    if (this.silenceMs >= SILENCE_FLUSH_MS) {
      this.flush();
    }
  }

  /** Flush the buffered utterance (VAD silence timeout or manual Enter). */
  flush(): void {
    if (!this.speechDetected || this.bufferedMs < MIN_UTTERANCE_MS) {
      this.resetUtterance();
      return;
    }
    const samples = this.concatBuffer();
    const durMs = (samples.length / this.sampleRate) * 1000;
    const peak = computeRmsEnergy(samples);
    console.warn(`[energy-vad] flush: ${samples.length} samples (~${durMs.toFixed(0)}ms), peak energy ${peak.toFixed(3)}, frames=${this.buffer.length}`);
    this.resetUtterance();
    if (samples.length > 0) {
      this.callbacks.onUtterance(encodeWavToBlob(samples));
    }
  }

  /** Manual flush (Enter key) — sends whatever has been heard so far. */
  sendNow(): void {
    this.flush();
  }

  /** Stop buffering during ASR/chat/TTS so a reply isn't transcribed as speech. */
  suspendCapture(): void {
    this.capturePaused = true;
    this.resetUtterance();
    this._userSpeaking = false;
  }

  resumeCapture(): void {
    this.capturePaused = false;
  }

  private resetUtterance(): void {
    this.buffer = [];
    this.bufferedMs = 0;
    this.silenceMs = 0;
    this.speechDetected = false;
    this._userSpeaking = false;
  }

  private concatBuffer(): Float32Array {
    let total = 0;
    for (const chunk of this.buffer) total += chunk.length;
    const out = new Float32Array(total);
    let offset = 0;
    for (const chunk of this.buffer) {
      out.set(chunk, offset);
      offset += chunk.length;
    }
    return out;
  }

  pause(): void {
    this._listening = false;
    this._userSpeaking = false;
    this.processor?.disconnect();
    this.processor = null;
    this.source?.disconnect();
    this.source = null;
    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = null;
  }

  resume(): void {
    void this.start();
  }

  destroy(): void {
    this.destroyed = true;
    this.pause();
    if (this.audioContext) {
      void this.audioContext.close();
      this.audioContext = null;
    }
    this.resetUtterance();
  }
}
