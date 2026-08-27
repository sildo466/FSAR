// SPDX-License-Identifier: MIT
export interface EmotionState {
  affection?: number;
  trust?: number;
  mood?: number;
  energy?: number;
  [key: string]: number | undefined;
}

export interface AvatarRenderer {
  load(url: string): Promise<void>;
  start(): void;
  stop(): void;
  setEmotion(state: EmotionState): void; // no-op until Stage 3
  dispose(): void;
  // speak() reserved for Stage 3 (mouth binding to audio)
}