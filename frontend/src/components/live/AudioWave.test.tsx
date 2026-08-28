// SPDX-License-Identifier: MIT
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render } from "@testing-library/react";
import { AudioWave } from "./AudioWave";

const mocks = vi.hoisted(() => ({
  subscribe: vi.fn((_cb: (level: number) => void) => () => {}),
}));

vi.mock("../../stores/speech", () => ({
  useSpeechStore: {
    getState: () => ({
      subscribeAudioLevel: mocks.subscribe,
    }),
  },
}));

afterEach(() => cleanup());

describe("AudioWave", () => {
  it("subscribes to the audio level on mount", () => {
    render(<AudioWave />);
    expect(mocks.subscribe).toHaveBeenCalledTimes(1);
  });

  it("renders a set of bars", () => {
    render(<AudioWave />);
    const wave = document.querySelector("[data-testid='live-wave']");
    expect(wave).toBeTruthy();
    expect(wave!.querySelectorAll("span").length).toBeGreaterThan(0);
  });
});
