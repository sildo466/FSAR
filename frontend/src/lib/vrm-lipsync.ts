// SPDX-License-Identifier: MIT
import type { WLipSyncAudioNode, Profile } from "wlipsync";

export const PHONEMES = ["A", "E", "I", "O", "U"] as const;
export type Phoneme = (typeof PHONEMES)[number];

/** VRM expression preset name per phoneme. */
export const PHONEME_TO_VRM: Record<Phoneme, string> = {
  A: "aa",
  E: "ee",
  I: "ih",
  O: "oh",
  U: "ou",
};

export interface LipsyncFrame {
  /** Mouth openness in 0..1, derived from the audio energy. */
  volume: number;
  /** Per-phoneme weights in 0..1; at most two are non-zero (top-2 blend). */
  weights: Record<Phoneme, number>;
}

/** Volume below this is treated as silence and closes the mouth. */
const SILENCE_THRESHOLD = 0.06;
/** Higher = snappier mouth, lower = smoother. */
const SMOOTHING = 0.45;
/** Non-linear energy curve: small sounds move the mouth less. */
const ENERGY_CURVE = 1.4;

function clamp01(v: number): number {
  return v < 0 ? 0 : v > 1 ? 1 : v;
}

/**
 * Pure: maps raw wlipsync weights (any key names) to our phoneme set,
 * blending the top two phonemes and damping toward silence.
 */
export function computeFrame(
  rawWeights: Record<string, number>,
  rawVolume: number,
  prev: LipsyncFrame | null = null,
): LipsyncFrame {
  const candidates: { phoneme: Phoneme; weight: number }[] = [];
  for (const p of PHONEMES) {
    const w = clamp01(rawWeights[p] ?? 0);
    if (w > 0) candidates.push({ phoneme: p, weight: w });
  }
  candidates.sort((a, b) => b.weight - a.weight);
  const top = candidates.slice(0, 2);

  const weights: Record<Phoneme, number> = { A: 0, E: 0, I: 0, O: 0, U: 0 };
  if (top.length > 0) {
    const sum = top.reduce((acc, c) => acc + c.weight, 0);
    const target = Math.min(1, sum);
    for (const c of top) {
      weights[c.phoneme] = sum > 0 ? (c.weight / sum) * target : 0;
    }
  }

  const volume = Math.pow(clamp01(rawVolume), ENERGY_CURVE);
  const silent = volume <= SILENCE_THRESHOLD;
  const target = silent ? { volume: 0, weights: { A: 0, E: 0, I: 0, O: 0, U: 0 } } : { volume, weights };

  if (!prev) return target;

  const t = SMOOTHING;
  const smooth = (a: number, b: number) => a + (b - a) * t;
  return {
    volume: smooth(prev.volume, target.volume),
    weights: {
      A: smooth(prev.weights.A, target.weights.A),
      E: smooth(prev.weights.E, target.weights.E),
      I: smooth(prev.weights.I, target.weights.I),
      O: smooth(prev.weights.O, target.weights.O),
      U: smooth(prev.weights.U, target.weights.U),
    },
  };
}

/**
 * Wraps a wlipsync AudioWorkletNode: creates it, taps an audio source into it,
 * and exposes per-frame phoneme state for the avatar update loop.
 */
export class VrmLipsync {
  readonly node: WLipSyncAudioNode;
  private frame: LipsyncFrame = { volume: 0, weights: { A: 0, E: 0, I: 0, O: 0, U: 0 } };

  private constructor(node: WLipSyncAudioNode) {
    this.node = node;
  }

  static async create(context: AudioContext, profile: Profile): Promise<VrmLipsync> {
    // Dynamic import keeps the wlipsync worklet glue (which references
    // AudioWorkletNode) out of module scope in non-browser environments.
    const { createWLipSyncNode } = await import("wlipsync");
    const node = await createWLipSyncNode(context, profile);
    return new VrmLipsync(node);
  }

  /** Route audio through the lip-sync node (call before starting playback). */
  connect(source: AudioNode): void {
    source.connect(this.node);
  }

  /** Read the latest frame; call once per animation frame. */
  read(): LipsyncFrame {
    this.frame = computeFrame(this.node.weights, this.node.volume, this.frame);
    return this.frame;
  }
}
