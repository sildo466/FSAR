// SPDX-License-Identifier: MIT
import { afterEach, beforeAll, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ClientMsg } from "../../lib/ws-client";
import { initI18n } from "../../lib/i18nSetup";
import { useWS } from "../../stores/ws";
import { StepTts } from "./StepTts";

class Client { sent: ClientMsg[] = []; send(message: ClientMsg) { this.sent.push(message); } }

beforeAll(async () => {
  await initI18n("en");
});

afterEach(cleanup);

it("renders seven presets and saves an Edge provider", () => {
  const client = new Client();
  const onNext = vi.fn();
  useWS.setState({ client: client as never, config: { tts: { active: "", providers: [] } } });
  render(<StepTts onNext={onNext} onSkip={() => {}} />);
  expect(screen.getAllByRole("button").filter((button) => button.textContent?.match(/Microsoft Edge|OpenAI|ElevenLabs|Azure|DashScope|Volcengine|MiniMax/))).toHaveLength(7);
  fireEvent.click(screen.getByRole("button", { name: /Microsoft Edge/ }));
  fireEvent.change(screen.getByLabelText("Voice ID"), { target: { value: "zh-CN-XiaoxiaoNeural" } });
  fireEvent.click(screen.getByRole("button", { name: "Save & Next" }));
  expect(client.sent.some((message) => message.type === "settings.patch")).toBe(true);
  expect(onNext).toHaveBeenCalled();
});

it("skips without writing providers", () => {
  const client = new Client();
  useWS.setState({ client: client as never, config: { tts: { active: "", providers: [] } } });
  render(<StepTts onNext={() => {}} onSkip={() => {}} />);
  fireEvent.click(screen.getByRole("button", { name: "Skip setup" }));
  expect(client.sent).toEqual([{ type: "onboarding.skip_step", step: "tts" }]);
});
