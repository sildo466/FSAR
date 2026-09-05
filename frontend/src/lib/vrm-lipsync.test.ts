// SPDX-License-Identifier: MIT
import { describe, expect, it } from "vitest";
import { computeFrame, PHONEME_TO_VRM } from "./vrm-lipsync";
import { mapEmotionState } from "../components/live/VrmAvatar";

describe("computeFrame", () => {
  it("blends the top two phonemes and normalizes their sum", () => {
    const frame = computeFrame({ A: 0.8, E: 0.4, I: 0.1 }, 0.9);
    expect(frame.weights.A).toBeGreaterThan(0);
    expect(frame.weights.E).toBeGreaterThan(0);
    expect(frame.weights.I).toBe(0);
    const active = frame.weights.A + frame.weights.E;
    expect(active).toBeCloseTo(Math.min(1, 0.8 + 0.4), 5);
    expect(frame.weights.A).toBeGreaterThan(frame.weights.E);
  });

  it("applies a non-linear energy curve to the volume", () => {
    const quiet = computeFrame({ A: 1 }, 0.2);
    const loud = computeFrame({ A: 1 }, 0.9);
    expect(quiet.volume).toBeLessThan(0.2);
    expect(loud.volume).toBeCloseTo(0.9 ** 1.4, 5);
    expect(loud.volume).toBeGreaterThan(quiet.volume);
  });

  it("treats near-silence as closed mouth", () => {
    const frame = computeFrame({ A: 0.9 }, 0.02);
    expect(frame.volume).toBe(0);
    expect(frame.weights.A).toBe(0);
  });

  it("smooths toward the target when a previous frame exists", () => {
    const prev = computeFrame({ A: 1 }, 0.9);
    const next = computeFrame({ A: 0, E: 1 }, 0.9, prev);
    expect(next.weights.A).toBeGreaterThan(0);
    expect(next.weights.A).toBeLessThan(1);
    expect(next.weights.E).toBeGreaterThan(0);
  });

  it("maps every phoneme to a VRM expression preset", () => {
    expect(PHONEME_TO_VRM.A).toBe("aa");
    expect(PHONEME_TO_VRM.E).toBe("ee");
    expect(PHONEME_TO_VRM.I).toBe("ih");
    expect(PHONEME_TO_VRM.O).toBe("oh");
    expect(PHONEME_TO_VRM.U).toBe("ou");
  });
});

describe("mapEmotionState", () => {
  it("maps strongly negative mood to sad", () => {
    const r = mapEmotionState({ mood: -80, affection: 50, trust: 50, energy: 50 });
    expect(r.preset).toBe("sad");
    expect(r.intensity).toBeGreaterThan(0.5);
  });

  it("maps negative mood with low trust to angry", () => {
    const r = mapEmotionState({ mood: -15, affection: 30, trust: 20, energy: 50 });
    expect(r.preset).toBe("angry");
  });

  it("maps low energy with decent affection to relaxed", () => {
    const r = mapEmotionState({ mood: 0, affection: 70, trust: 50, energy: 10 });
    expect(r.preset).toBe("relaxed");
    expect(r.intensity).toBeGreaterThan(0.5);
  });

  it("maps high mood + energy to happy", () => {
    const r = mapEmotionState({ mood: 60, affection: 60, trust: 50, energy: 80 });
    expect(r.preset).toBe("happy");
  });

  it("maps high affection + energy to surprised", () => {
    const r = mapEmotionState({ mood: 10, affection: 90, trust: 50, energy: 85 });
    expect(r.preset).toBe("surprised");
  });

  it("falls back to a neutral relaxed default", () => {
    const r = mapEmotionState({ mood: 0, affection: 50, trust: 50, energy: 50 });
    expect(r.preset).toBe("relaxed");
    expect(r.intensity).toBeLessThanOrEqual(0.2);
  });

  it("clamps out-of-range inputs", () => {
    const r = mapEmotionState({ mood: 1000, affection: 999, trust: -1, energy: 500 });
    expect(r.intensity).toBeLessThanOrEqual(1);
  });
});
