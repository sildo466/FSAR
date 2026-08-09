// SPDX-License-Identifier: MIT
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { TtsVoiceField } from "./TtsVoiceField";
import { useSpeechStore } from "../../stores/speech";
import { useWS } from "../../stores/ws";
import { initI18n } from "../../lib/i18nSetup";

afterEach(cleanup);

beforeEach(async () => {
  await initI18n("en");
});

it("locks the character voice when TTS is not configured", () => {
  useSpeechStore.setState({ isTtsConfigured: false });
  useWS.setState({ config: { tts: { active: "", providers: [] } } });
  render(<TtsVoiceField value="" onChange={() => {}} instructions="" onInstructionsChange={() => {}} autoplay={false} onAutoplayChange={() => {}} />);
  expect(screen.getByRole("combobox")).toBeDisabled();
  screen.getAllByRole("textbox").forEach((element) => expect(element).toBeDisabled());
  expect(screen.getByRole("link", { name: "Configure now" })).toHaveAttribute("href", "/settings/speech");
});

it("updates an enabled voice field", () => {
  const onChange = vi.fn();
  useSpeechStore.setState({ isTtsConfigured: true });
  useWS.setState({ config: { tts: { active: "p1", providers: [{ id: "p1", preset_id: "openai" }] } } });
  render(<TtsVoiceField value="" onChange={onChange} instructions="" onInstructionsChange={() => {}} autoplay={false} onAutoplayChange={() => {}} />);
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "alloy" } });
  expect(onChange).toHaveBeenCalledWith("alloy");
});

it("updates the per-character instructions", () => {
  const onInstructionsChange = vi.fn();
  useSpeechStore.setState({ isTtsConfigured: true });
  useWS.setState({ config: { tts: { active: "p1", providers: [{ id: "p1", preset_id: "qwen-tts" }] } } });
  render(<TtsVoiceField value="" onChange={() => {}} instructions="" onInstructionsChange={onInstructionsChange} autoplay={false} onAutoplayChange={() => {}} />);
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "cheerful" } });
  expect(onInstructionsChange).toHaveBeenCalledWith("cheerful");
});
