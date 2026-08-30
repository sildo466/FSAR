// SPDX-License-Identifier: MIT
import type * as THREE from "three";

export interface EmotionState {
  affection?: number;
  trust?: number;
  mood?: number;
  energy?: number;
  [key: string]: number | undefined;
}

export interface AvatarRenderer {
  readonly object: THREE.Object3D;
  load(url: string): Promise<void>;
  start(): void;
  stop(): void;
  setEmotion(state: EmotionState): void;
  /** Begin mouth animation; driven by a lipsync source while speaking. */
  speak(): void;
  /** End mouth animation and relax back to idle. */
  stopSpeaking(): void;
  dispose(): void;
}