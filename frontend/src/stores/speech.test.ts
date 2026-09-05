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
    class FakeAudioContext {
      currentTime = 0;
      destination = {};
      audioWorklet = {
        addModule: async () => {
          throw new Error("no worklet in tests");
        },
      };
      async decodeAudioData() {
        return { duration: 3 };
      }
      createBufferSource() {
        const source: {
          buffer: unknown;
          startTime: number;
          onended?: () => void;
          connect: () => void;
          start: () => void;
          stop: () => void;
        } = {
          buffer: null,
          startTime: 0,
          connect: () => {},
          start: () => {
            setTimeout(() => source.onended?.(), 0);
          },
          stop: () => {},
        };
        return source;
      }
      createAnalyser() {
        return {
          fftSize: 0,
          smoothingTimeConstant: 0,
          frequencyBinCount: 64,
          connect: () => {},
          getByteFrequencyData: (arr: Uint8Array) => arr.fill(0),
        };
      }
      async resume() {}
    }
    vi.stubGlobal("AudioContext", FakeAudioContext);
    vi.stubGlobal(
      "fetch",
      async () => ({ arrayBuffer: async () => new ArrayBuffer(8) }) as Response,
    );
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
