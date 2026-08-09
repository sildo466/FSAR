// SPDX-License-Identifier: MIT
import { afterEach, beforeEach, expect, it } from "vitest";
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { TtsProviderCard, type TtsProvider } from "./TtsProviderCard";
import { initI18n } from "../../lib/i18nSetup";

afterEach(cleanup);

beforeEach(async () => {
  await initI18n("en");
});

function provider(model: string): TtsProvider {
  return {
    id: "p1",
    preset_id: "qwen-tts",
    label: "Qwen-TTS",
    family: "dashscope",
    base_url: "https://dashscope.aliyuncs.com/api/v1",
    api_key: "sk",
    voice: "Cherry",
    model,
    enabled: true,
  };
}

it("shows style instructions for qwen models", () => {
  render(<TtsProviderCard provider={provider("qwen3-tts-instruct-flash")} active onChange={() => {}} />);
  expect(screen.getByPlaceholderText(/Speak gently/)).toBeInTheDocument();
});

it("hides style instructions for non-qwen dashscope models", () => {
  render(<TtsProviderCard provider={provider("cosyvoice-v2")} active onChange={() => {}} />);
  expect(screen.queryByPlaceholderText(/Speak gently/)).toBeNull();
});

it("renders no built-in voice suggestions for qwen-tts", () => {
  const { container } = render(<TtsProviderCard provider={provider("qwen3-tts-flash")} active onChange={() => {}} />);
  expect(container.querySelectorAll("datalist option").length).toBe(0);
});
