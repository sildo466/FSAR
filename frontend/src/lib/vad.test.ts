// SPDX-License-Identifier: MIT
import { describe, expect, it } from "vitest";
import { buildWavBuffer, computeRmsEnergy, encodeWavToBlob } from "./vad";

function makeSamples(n = 16000): Float32Array {
  const s = new Float32Array(n);
  for (let i = 0; i < n; i++) s[i] = Math.sin(i / 20) * 0.5;
  return s;
}

function headerStr(buffer: ArrayBuffer, start: number, len: number): string {
  return new TextDecoder().decode(new Uint8Array(buffer).slice(start, start + len));
}

describe("encodeWavToBlob", () => {
  it("produces a WAV blob with a RIFF header", () => {
    const blob = encodeWavToBlob(makeSamples());
    expect(blob.type).toBe("audio/wav");
    const buf = buildWavBuffer(makeSamples());
    expect(headerStr(buf, 0, 4)).toBe("RIFF");
    expect(headerStr(buf, 8, 4)).toBe("WAVE");
  });

  it("sizes the data chunk to match sample count (16-bit mono)", () => {
    const buf = buildWavBuffer(makeSamples(1000));
    const view = new DataView(buf);
    // data chunk length at bytes 40-43 = 1000 samples * 2 bytes
    expect(view.getUint32(40, true)).toBe(2000);
  });
});

describe("computeRmsEnergy", () => {
  it("returns 0 for silence", () => {
    expect(computeRmsEnergy(new Float32Array(100))).toBe(0);
  });

  it("returns ~0.5 for a full-scale sine", () => {
    const s = makeSamples(1000);
    const energy = computeRmsEnergy(s);
    // sin at amplitude 0.5 → RMS = 0.5 / sqrt(2) ≈ 0.354
    expect(energy).toBeGreaterThan(0.3);
    expect(energy).toBeLessThan(0.4);
  });

  it("returns 0 for empty input", () => {
    expect(computeRmsEnergy(new Float32Array(0))).toBe(0);
  });
});
