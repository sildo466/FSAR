// SPDX-License-Identifier: MIT
import { MicVAD } from "@ricky0123/vad-web";
import { VAD_ASSET_BASE_PATH } from "./vadAssets";

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

interface LiveVadCallbacks {
  onSpeechEnd: (blob: Blob) => void;
  onError?: (error: unknown) => void;
}

export class LiveVad {
  private vad: MicVAD | null = null;
  private callbacks: LiveVadCallbacks;
  private _listening = false;
  private _userSpeaking = false;

  constructor(callbacks: LiveVadCallbacks) {
    this.callbacks = callbacks;
  }

  get listening(): boolean {
    return this._listening;
  }

  get userSpeaking(): boolean {
    return this._userSpeaking;
  }

  async start(): Promise<void> {
    this.destroy();
    this.vad = await MicVAD.new({
      model: "v5",
      baseAssetPath: VAD_ASSET_BASE_PATH,
      onnxWASMBasePath: VAD_ASSET_BASE_PATH,
      stream: true,
      onSpeechStart: () => {
        this._userSpeaking = true;
      },
      onSpeechEnd: (audio: Float32Array) => {
        this._userSpeaking = false;
        if (audio.length === 0) return;
        this.callbacks.onSpeechEnd(encodeWavToBlob(audio));
      },
      onError: (error) => {
        this.callbacks.onError?.(error);
      },
    });
    await this.vad.start();
    this._listening = true;
  }

  pause(): void {
    if (this.vad) void this.vad.pause();
    this._listening = false;
    this._userSpeaking = false;
  }

  resume(): void {
    if (!this.vad) return;
    void this.vad.start();
    this._listening = true;
  }

  destroy(): void {
    if (this.vad) {
      void this.vad.pause();
      void this.vad.destroy();
      this.vad = null;
    }
    this._listening = false;
    this._userSpeaking = false;
  }
}
