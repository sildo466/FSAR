// SPDX-License-Identifier: MIT
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useSpeechStore } from "./speech";
import { useWS } from "./ws";

describe("useSpeechStore", () => {
  beforeEach(() => {
    useSpeechStore.setState({ isTtsConfigured: false, isAsrConfigured: false, autoplay: false });
  });

  it("derives speech availability from the config snapshot", () => {
    useSpeechStore.getState().syncConfig({
      tts: { active: "p1", autoplay: true },
      asr: { active: "" },
    });
    expect(useSpeechStore.getState().isTtsConfigured).toBe(true);
    expect(useSpeechStore.getState().isAsrConfigured).toBe(false);
    expect(useSpeechStore.getState().autoplay).toBe(true);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("sends instructions_override in the tts.synthesize message", async () => {
    class FakeAudio {
      onended: (() => void) | null = null;
      onerror: (() => void) | null = null;
      ontimeupdate: (() => void) | null = null;
      play() {
        this.onended?.();
        return Promise.resolve();
      }
      pause() {}
    }
    vi.stubGlobal("Audio", FakeAudio);
    useSpeechStore.setState({ isTtsConfigured: true });
    const sent: Array<Record<string, unknown>> = [];
    let responder: ((message: Record<string, unknown>) => void) | null = null;
    useWS.setState({
      client: {
        on: (handler: (message: Record<string, unknown>) => void) => {
          responder = handler;
          return () => {};
        },
        send: (message: Record<string, unknown>) => {
          sent.push(message);
          responder?.({
            type: "tts.audio",
            request_id: message.request_id,
            mime: "audio/mpeg",
            audio: "",
          });
        },
      } as never,
    });
    await useSpeechStore
      .getState()
      .playText("hi", "m1", { instructionsOverride: "cheerful" });
    expect(sent[0]).toMatchObject({
      type: "tts.synthesize",
      instructions_override: "cheerful",
    });
  });
});
