// SPDX-License-Identifier: MIT
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { VRMLoaderPlugin, VRMUtils } from "@pixiv/three-vrm";
import type { VRM } from "@pixiv/three-vrm";
import type { AvatarRenderer, EmotionState } from "./AvatarRenderer";
import { PHONEME_TO_VRM, type Phoneme } from "../../lib/vrm-lipsync";
import { getActiveLipsync } from "../../stores/speech";

const BLINK_INTERVAL_MS = 3200;
const BLINK_CLOSE_MS = 140;
const BREATH_AMPLITUDE = 0.008;
const MOUTH_DECAY = 0.3;
const EMOTION_LERP = 0.08;

const EXPRESSIONS = ["happy", "angry", "sad", "relaxed", "surprised"] as const;
export type ExpressionPreset = (typeof EXPRESSIONS)[number];

export interface EmotionTarget {
  preset: ExpressionPreset;
  /** How strongly the preset is applied, 0..1. */
  intensity: number;
}

export function clamp01(v: number): number {
  return v < 0 ? 0 : v > 1 ? 1 : v;
}

/**
 * Pure: maps the numeric emotion layer (mood/affection/trust/energy) to a
 * VRM expression preset + intensity. Mood dominates; the other axes tune it.
 */
export function mapEmotionState(state: EmotionState): EmotionTarget {
  const mood = state.mood ?? 0;
  const affection = state.affection ?? 50;
  const trust = state.trust ?? 50;
  const energy = state.energy ?? 50;
  const moodN = clamp01((mood + 100) / 200); // 0..1
  const affectionN = clamp01(affection / 100);
  const trustN = clamp01(trust / 100);
  const energyN = clamp01(energy / 100);

  if (mood <= -25) {
    return { preset: "sad", intensity: 0.5 + 0.5 * (1 - moodN) };
  }
  if (mood <= -8 && trustN < 0.4) {
    return { preset: "angry", intensity: 0.5 + 0.5 * (1 - trustN) };
  }
  if (energyN < 0.3 && affectionN >= 0.55) {
    return { preset: "relaxed", intensity: 0.4 + 0.6 * (1 - energyN) };
  }
  if (mood >= 20 && energyN >= 0.6) {
    return { preset: "happy", intensity: 0.5 + 0.3 * moodN + 0.2 * energyN };
  }
  if (affectionN >= 0.7 && energyN >= 0.75) {
    return { preset: "surprised", intensity: 0.5 + 0.5 * energyN };
  }
  if (mood >= 5) {
    return { preset: "happy", intensity: 0.25 + 0.5 * moodN };
  }
  return { preset: "relaxed", intensity: 0.2 };
}

export class VrmAvatar implements AvatarRenderer {
  private vrm: VRM | null = null;
  private group = new THREE.Group();
  private clock = new THREE.Clock();
  private nextBlinkAt = 0;
  private blinkStartedAt = -1;
  private running = false;
  private raf = 0;
  private speaking = false;
  private mouthWeights: Record<Phoneme, number> = { A: 0, E: 0, I: 0, O: 0, U: 0 };
  private emotionValues: Record<ExpressionPreset, number> = {
    happy: 0,
    angry: 0,
    sad: 0,
    relaxed: 0,
    surprised: 0,
  };
  private emotionTarget: EmotionTarget = { preset: "relaxed", intensity: 0 };

  async load(url: string): Promise<void> {
    const loader = new GLTFLoader();
    loader.register((parser) => new VRMLoaderPlugin(parser));
    const gltf = await loader.loadAsync(url);
    const vrm: VRM = gltf.userData.vrm;
    VRMUtils.removeUnnecessaryJoints(gltf.scene);
    this.disposeVrm();
    this.vrm = vrm;
    VRMUtils.rotateVRM0(vrm);
    this.group.add(gltf.scene);
  }

  get object(): THREE.Object3D {
    return this.group;
  }

  start(): void {
    if (this.running) return;
    this.running = true;
    this.clock.start();
    this.nextBlinkAt = performance.now() + BLINK_INTERVAL_MS;
    const tick = () => {
      if (!this.running) return;
      const dt = this.clock.getDelta();
      this.vrm?.update(dt);
      this.animateBreath(performance.now());
      this.animateBlink(performance.now());
      this.animateMouth();
      this.animateEmotion();
      this.raf = requestAnimationFrame(tick);
    };
    tick();
  }

  stop(): void {
    this.running = false;
    cancelAnimationFrame(this.raf);
  }

  speak(): void {
    this.speaking = true;
  }

  stopSpeaking(): void {
    this.speaking = false;
  }

  setEmotion(state: EmotionState): void {
    this.emotionTarget = mapEmotionState(state);
  }

  dispose(): void {
    this.stop();
    this.disposeVrm();
  }

  private animateBreath(now: number): void {
    if (!this.vrm) return;
    const t = now / 1000;
    this.group.position.y = Math.sin(t * 1.6) * BREATH_AMPLITUDE;
  }

  private animateBlink(now: number): void {
    const manager = this.vrm?.expressionManager;
    if (!manager || manager.getExpression("blink") === null) return;
    if (this.blinkStartedAt < 0 && now >= this.nextBlinkAt) {
      this.blinkStartedAt = now;
      this.nextBlinkAt = now + BLINK_INTERVAL_MS;
    }
    if (this.blinkStartedAt >= 0) {
      const el = (now - this.blinkStartedAt) / BLINK_CLOSE_MS;
      const closing = el <= 1 ? el : Math.max(0, 2 - el);
      manager.setValue("blink", closing);
      if (el >= 2) this.blinkStartedAt = -1;
    }
  }

  private animateMouth(): void {
    const manager = this.vrm?.expressionManager;
    if (!manager) return;
    const lipsync = getActiveLipsync();
    if (this.speaking && lipsync) {
      const frame = lipsync.read();
      this.mouthWeights = {
        A: frame.weights.A * frame.volume,
        E: frame.weights.E * frame.volume,
        I: frame.weights.I * frame.volume,
        O: frame.weights.O * frame.volume,
        U: frame.weights.U * frame.volume,
      };
    } else {
      // Relax the mouth back to closed.
      for (const p of Object.keys(this.mouthWeights) as Phoneme[]) {
        this.mouthWeights[p] *= 1 - MOUTH_DECAY;
        if (this.mouthWeights[p] < 0.005) this.mouthWeights[p] = 0;
      }
    }
    for (const p of Object.keys(this.mouthWeights) as Phoneme[]) {
      const name = PHONEME_TO_VRM[p];
      if (manager.getExpression(name) !== null) {
        manager.setValue(name, this.mouthWeights[p]);
      }
    }
  }

  private animateEmotion(): void {
    const manager = this.vrm?.expressionManager;
    if (!manager) return;
    for (const preset of EXPRESSIONS) {
      const target = preset === this.emotionTarget.preset ? this.emotionTarget.intensity : 0;
      const value = this.emotionValues[preset] + (target - this.emotionValues[preset]) * EMOTION_LERP;
      this.emotionValues[preset] = value;
      if (manager.getExpression(preset) !== null) {
        manager.setValue(preset, value);
      }
    }
  }

  private disposeVrm(): void {
    if (this.vrm) {
      VRMUtils.deepDispose(this.vrm.scene);
      this.group.clear();
      this.vrm = null;
    }
  }
}
