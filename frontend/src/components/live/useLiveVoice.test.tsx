// SPDX-License-Identifier: MIT
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render } from "@testing-library/react";
import { useLiveVoice } from "./useLiveVoice";

const mocks = vi.hoisted(() => ({
  vad: {
    start: vi.fn(async () => {}),
    pause: vi.fn(),
    resume: vi.fn(),
    destroy: vi.fn(),
    ensureUnlocked: vi.fn(),
    sendNow: vi.fn(),
  } as {
    start: ReturnType<typeof vi.fn>;
    pause: ReturnType<typeof vi.fn>;
    resume: ReturnType<typeof vi.fn>;
    destroy: ReturnType<typeof vi.fn>;
    ensureUnlocked: ReturnType<typeof vi.fn>;
    sendNow: ReturnType<typeof vi.fn>;
    callbacks?: { onUtterance: (blob: Blob) => void; onSpeechStart?: () => void };
  },
  transcribeAudio: vi.fn(async () => "hello"),
  playText: vi.fn(async () => {}),
  stopAudio: vi.fn(),
  client: { on: vi.fn(() => () => {}), send: vi.fn() },
}));

vi.mock("../../lib/vad", () => ({
  encodeWavToBlob: vi.fn(() => new Blob()),
  EnergyVad: vi.fn().mockImplementation((callbacks: unknown) => {
    mocks.vad.callbacks = callbacks as typeof mocks.vad.callbacks;
    return mocks.vad;
  }),
}));

vi.mock("../../stores/speech", () => ({
  useSpeechStore: {
    getState: () => ({
      transcribeAudio: mocks.transcribeAudio,
      playText: mocks.playText,
      stopAudio: mocks.stopAudio,
      isAsrConfigured: true,
      isTtsConfigured: true,
    }),
  },
}));

vi.mock("../../stores/ws", () => ({
  useWS: { getState: () => ({ client: mocks.client }) },
}));

vi.mock("../../stores/sessions", () => ({
  useSessions: { getState: () => ({ liveHistory: {} }) },
}));

vi.mock("../../stores/cards", () => ({
  useCardsStore: { getState: () => ({ characters: [] }) },
}));

function Harness() {
  const r = useLiveVoice({ characterId: 1 });
  return (
    <div>
      <span data-testid="muted">{String(r.muted)}</span>
      <span data-testid="listening">{String(r.listening)}</span>
      <button onClick={r.toggleMute}>toggle</button>
      <button onClick={r.retryVad}>retry</button>
      <button onClick={r.sendNow}>enter</button>
    </div>
  );
}

afterEach(() => {
  cleanup();
  mocks.vad.callbacks = undefined;
  mocks.transcribeAudio.mockClear();
  mocks.client.send.mockClear();
});

describe("useLiveVoice", () => {
  it("starts the VAD on mount when ASR is configured", async () => {
    render(<Harness />);
    await new Promise((r) => setTimeout(r, 0));
    expect(mocks.vad.start).toHaveBeenCalledTimes(1);
  });

  it("transcribes on utterance and sends chat.send", async () => {
    render(<Harness />);
    await new Promise((r) => setTimeout(r, 0));
    mocks.vad.callbacks?.onUtterance(new Blob());
    await new Promise((r) => setTimeout(r, 0));
    expect(mocks.transcribeAudio).toHaveBeenCalledTimes(1);
    expect(mocks.client.send).toHaveBeenCalledWith(
      expect.objectContaining({ type: "chat.send", mode: "companion" })
    );
  });

  it("toggles mute by pausing/resuming the VAD", async () => {
    render(<Harness />);
    await new Promise((r) => setTimeout(r, 0));
    const buttons = document.querySelectorAll("button");
    buttons[0].click();
    expect(mocks.vad.pause).toHaveBeenCalled();
    buttons[0].click();
    expect(mocks.vad.resume).toHaveBeenCalled();
  });

  it("sendNow flushes the current utterance", async () => {
    render(<Harness />);
    await new Promise((r) => setTimeout(r, 0));
    const buttons = document.querySelectorAll("button");
    buttons[2].click();
    expect(mocks.vad.sendNow).toHaveBeenCalledTimes(1);
  });
});
