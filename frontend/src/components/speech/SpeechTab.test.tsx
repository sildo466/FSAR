// SPDX-License-Identifier: MIT
import { afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { initI18n } from "../../lib/i18nSetup";
import { SpeechTab } from "./SpeechTab";
import { useWS } from "../../stores/ws";
import { useSpeechStore } from "../../stores/speech";

beforeAll(async () => {
  await initI18n("en");
});

describe("SpeechTab", () => {
  beforeEach(() => {
    useWS.setState({ config: { tts: { active: "", providers: [] }, asr: { active: "", providers: [] } } });
    useSpeechStore.setState({ isTtsConfigured: false, isAsrConfigured: false, autoplay: false });
  });
  afterEach(cleanup);

  it("shows collapsed unconfigured sections", () => {
    render(<SpeechTab />);
    expect(screen.getByText("TTS not configured")).toBeInTheDocument();
    expect(screen.getByText("ASR not configured")).toBeInTheDocument();
  });

  it("reveals all seven TTS presets", () => {
    render(<SpeechTab />);
    fireEvent.click(screen.getAllByRole("button", { name: "Configure now" })[0]);
    expect(screen.getByRole("button", { name: /Microsoft Edge/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /MiniMax TTS/ })).toBeInTheDocument();
    expect(screen.getAllByRole("button").filter((button) => button.textContent?.match(/Microsoft Edge|OpenAI|ElevenLabs|Azure|DashScope|Volcengine|MiniMax/))).toHaveLength(7);
  });
});
